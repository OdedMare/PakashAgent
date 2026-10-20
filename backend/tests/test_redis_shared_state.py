"""Redis as shared state: the throttle, the live signals and the model queue.

What is asserted here is the two halves of the promise in
`common/redis_hub.py`:

- with Redis, all three hold across processes -- simulated by two
  instances sharing one server, which is all a second process is to them;
- without it, or when it stops answering, each behaves exactly as it did
  before Redis existed, rather than failing the request.

The shared half needs a real server. It runs against `PAKASH_TEST_REDIS_URL`
when set, otherwise against a `redis-server` started on a free port, and is
skipped when neither is available.
"""

import asyncio
import os
import shutil
import socket
import subprocess
import threading
import time
import uuid

import pytest

from app.common.errors import AuthError, TooManyAttemptsError
from app.common.events import TeamEvents
from app.common.redis_hub import RedisHub, mask_url, probe
from app.common.runtime_settings.runtime_settings import RuntimeSettings
from app.common.throttle import LoginThrottle
from app.dal.llm.model_slots import BACKGROUND, INTERACTIVE, ModelBusy, ModelSlots
from app.dal.llm.redis_slots import RedisModelSlots
from app.dal.llm.team_context import model_team


class _Store:
    def __init__(self, url="", password="", prefix="pakash"):
        self.settings = RuntimeSettings(
            database_url="", database_user="", database_password="",
            database_host="", database_port=None, database_name="",
            database_schema="", llm_model="", llm_diet_mode=False,
            llm_repetition_penalty=0.0, llm_timeout_seconds=0,
            llm_max_concurrency=1, llm_base_url=None, openai_api_key="",
            redis_url=url, redis_password=password, redis_key_prefix=prefix,
        )

    def get(self):
        return self.settings


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def redis_url():
    url = os.getenv("PAKASH_TEST_REDIS_URL")
    if url:
        yield url
        return
    binary = shutil.which("redis-server")
    if not binary:
        pytest.skip("no redis-server and no PAKASH_TEST_REDIS_URL")
    port = _free_port()
    process = subprocess.Popen(
        [binary, "--port", str(port), "--save", "", "--appendonly", "no"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = "redis://127.0.0.1:%d/0" % port
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    yield url
    process.terminate()
    process.wait(5)


@pytest.fixture
def hub(redis_url):
    # A fresh prefix per test: no test sees another's keys.
    return RedisHub(_Store(redis_url, prefix="t" + uuid.uuid4().hex[:8]))


def _refuse():
    raise AuthError("wrong")


# --- the hub -----------------------------------------------------------------

def test_no_url_means_no_client():
    assert RedisHub(_Store()).client() is None
    assert RedisHub(_Store()).status()["configured"] is False


def test_unreachable_redis_is_none_and_retried_later():
    clock = [0.0]
    calls = []

    def factory(url, password):
        calls.append(url)
        raise ConnectionError("refused")

    hub = RedisHub(
        _Store("redis://nowhere:1"), factory=factory, retry_seconds=5,
        clock=lambda: clock[0],
    )
    assert hub.client() is None
    assert hub.client() is None
    assert len(calls) == 1  # inside the back-off: not tried again
    clock[0] = 6
    assert hub.client() is None
    assert len(calls) == 2
    assert "refused" in hub.status()["error"]


def test_a_new_url_replaces_the_client(hub, redis_url):
    first = hub.client()
    hub._store.settings.redis_url = redis_url.replace("/0", "/1")
    second = hub.client()
    assert second is not None and second is not first


def test_mask_url_hides_the_password():
    assert mask_url("redis://:s3cret@host:6379/0") == "redis://:********@host:6379/0"
    assert mask_url("redis://host:6379") == "redis://host:6379"


def test_probe_reports_the_server(redis_url):
    report = probe(redis_url, "", "pakash")
    assert report["server"]["version"]
    assert report["app"]["model_calls"] == 0


# --- the throttle ------------------------------------------------------------

def test_lockout_is_shared_between_processes(hub):
    first = LoginThrottle(limit=3, redis=hub)
    second = LoginThrottle(limit=3, redis=hub)
    for throttle in (first, second, first):
        with pytest.raises(AuthError):
            throttle.attempt("boss:team", _refuse)
    # The third wrong guess was spread over two "processes" and still locked
    # the account for both.
    with pytest.raises(TooManyAttemptsError):
        second.attempt("boss:team", lambda: "ok")


def test_success_clears_the_shared_count(hub):
    throttle = LoginThrottle(limit=2, redis=hub)
    with pytest.raises(AuthError):
        throttle.attempt("employee:דנה", _refuse)
    assert throttle.attempt("employee:דנה", lambda: "ok") == "ok"
    with pytest.raises(AuthError):
        throttle.attempt("employee:דנה", _refuse)
    assert throttle.attempt("employee:דנה", lambda: "ok") == "ok"


def test_throttle_falls_back_to_memory_when_redis_fails(hub):
    throttle = LoginThrottle(limit=2, redis=hub)
    client = hub.client()
    client.connection_pool.disconnect()
    client.connection_pool.connection_kwargs["port"] = _free_port()
    for _ in range(2):
        with pytest.raises(AuthError):
            throttle.attempt("settings:x", _refuse)
    with pytest.raises(TooManyAttemptsError):
        throttle.attempt("settings:x", lambda: "ok")


# --- the live signals --------------------------------------------------------

def test_a_signal_crosses_processes(hub):
    publisher, listener = TeamEvents(redis=hub), TeamEvents(redis=hub)

    async def wait_for_signal():
        with listener.subscribe("team-a") as inbox:
            # Publish from another thread, as a sync route would, until the
            # listener's subscription is live.
            def keep_publishing():
                for _ in range(40):
                    publisher.publish("team-a", "requests")
                    time.sleep(0.05)

            threading.Thread(target=keep_publishing, daemon=True).start()
            return await asyncio.wait_for(inbox.get(), timeout=5)

    assert asyncio.run(wait_for_signal()) == "requests"


def test_a_signal_stays_in_its_team(hub):
    publisher, listener = TeamEvents(redis=hub), TeamEvents(redis=hub)

    async def scenario():
        with listener.subscribe("team-a") as inbox:
            await asyncio.sleep(1.5)  # let the listener subscribe
            publisher.publish("team-b", "swaps")
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(inbox.get(), timeout=0.5)

    asyncio.run(scenario())


def test_without_redis_delivery_stays_local():
    events = TeamEvents(redis=RedisHub(_Store()))

    async def scenario():
        with events.subscribe("team-a") as inbox:
            events.publish("team-a", "requests")
            return await asyncio.wait_for(inbox.get(), timeout=1)

    assert asyncio.run(scenario()) == "requests"


# --- the model queue ---------------------------------------------------------

def _slots(hub, limit=1, fallback=None, **kwargs):
    store = hub._store
    store.settings.llm_max_concurrency = limit
    fallback = fallback or ModelSlots(limit)
    return RedisModelSlots(store, hub, lambda: fallback, poll_seconds=0.02, **kwargs)


def _in_team(slots, team, priority, order, name, started=None):
    def run():
        with model_team(team), slots.reserve(priority):
            order.append(name)
            if started is not None:
                started.wait(5)
    return threading.Thread(target=run)


def test_the_limit_holds_across_processes(hub):
    first, second = _slots(hub), _slots(hub)
    with model_team("a"), first.reserve():
        with model_team("b"):
            with pytest.raises(ModelBusy):
                with second.reserve(timeout=0.3):
                    pass
    with second.reserve(timeout=1):
        pass


def test_the_limit_is_read_live(hub):
    slots = _slots(hub, limit=1)
    with model_team("a"), slots.reserve():
        hub._store.settings.llm_max_concurrency = 2
        with model_team("b"), slots.reserve(timeout=1):
            pass


def test_one_call_per_team_does_not_block_other_teams(hub):
    slots = _slots(hub, limit=2)
    with model_team("a"), slots.reserve():
        # Team a's second call waits for its first...
        with pytest.raises(ModelBusy):
            with slots.reserve(timeout=0.3):
                pass
        # ...but team b, queued behind it, gets the free slot.
        with model_team("b"), slots.reserve(timeout=1):
            pass


def test_interactive_work_goes_ahead_of_background(hub):
    slots = _slots(hub)
    order, release = [], threading.Event()
    holder = _in_team(slots, "a", INTERACTIVE, order, "first", release)
    holder.start()
    time.sleep(0.2)
    build = _in_team(slots, "b", BACKGROUND, order, "build")
    build.start()
    time.sleep(0.2)  # the build is queued first...
    chat = _in_team(slots, "c", INTERACTIVE, order, "chat")
    chat.start()
    time.sleep(0.2)
    release.set()
    for thread in (holder, build, chat):
        thread.join(5)
    assert order == ["first", "chat", "build"]  # ...and the chat goes first


def test_a_dead_holder_frees_its_slot(hub):
    dead = _slots(hub, lease_seconds=0.5)
    with model_team("a"):
        held = dead._acquire(hub.client(), INTERACTIVE, None)
    held._stop.set()  # the process died: nobody renews the lease
    started = time.monotonic()
    with model_team("b"), _slots(hub).reserve(timeout=5):
        pass
    assert time.monotonic() - started < 3


def test_without_redis_the_fallback_holds_the_line():
    fallback = ModelSlots(1)
    hub = RedisHub(_Store())
    slots = RedisModelSlots(hub._store, hub, lambda: fallback)
    with slots.reserve():
        with pytest.raises(ModelBusy):
            with fallback.reserve(timeout=0.05):
                pass
