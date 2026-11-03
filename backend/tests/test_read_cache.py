"""The read cache (D50): kept until the team writes, never required.

What is asserted is the promise in `common/read_cache.py`:

- with Redis, a read is answered from it until a write of its team (or one
  with no team) retires it, and every key starts with the chosen prefix;
- without Redis, with a TTL of 0, or with a Redis that stops answering,
  every read goes to its loader exactly as if the cache did not exist;
- a write that could not reach Redis is paid for before anything cached is
  trusted again.

The Redis half needs a real server: `PAKASH_TEST_REDIS_URL` when set,
otherwise a `redis-server` started on a free port; skipped without either.
"""

import os
import shutil
import socket
import subprocess
import time
import uuid
from types import SimpleNamespace

import pytest

from app.common.read_cache import ReadCache
from app.common.redis_hub import RedisHub, mask_url, probe


def _store(url="", prefix="pakash", ttl=300, password=""):
    settings = SimpleNamespace(
        redis_url=url, redis_host="", redis_port=None, redis_username="",
        redis_password=password, redis_key_prefix=prefix,
        redis_cache_ttl_seconds=ttl,
    )
    return SimpleNamespace(get=lambda: settings, settings=settings)


class _Loader:
    def __init__(self, value):
        self.value, self.calls = value, 0

    def __call__(self):
        self.calls += 1
        return self.value


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
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.05)
    yield "redis://127.0.0.1:%d/0" % port
    process.terminate()
    process.wait(5)


@pytest.fixture
def prefix():
    return "test-%s" % uuid.uuid4().hex[:8]


def _cache(url, prefix, ttl=300, today="2026-11-03"):
    store = _store(url, prefix, ttl)
    hub = RedisHub(store)
    return ReadCache(hub, store, today=lambda: today), hub, store


# --- without Redis -----------------------------------------------------------

def test_with_no_redis_every_read_goes_to_the_loader():
    cache, _, _ = _cache("", "pakash")
    load = _Loader({"n": 1})
    assert cache.read("t1", "stats", ("a",), load) == {"n": 1}
    assert cache.read("t1", "stats", ("a",), load) == {"n": 1}
    assert load.calls == 2
    cache.written({"t1"})  # nothing to tell, and nothing raised


def test_an_unreachable_redis_reads_postgres_and_does_not_raise():
    cache, hub, _ = _cache("redis://127.0.0.1:1/0", "pakash")
    load = _Loader([1, 2])
    assert cache.read("t1", "overview", (), load) == [1, 2]
    assert cache.read("t1", "overview", (), load) == [1, 2]
    assert load.calls == 2
    assert hub.status()["connected"] is False


def test_the_answer_is_json_ready_whichever_way_it_came():
    import datetime

    cache, _, _ = _cache("", "pakash")
    value = cache.read("t1", "x", (), lambda: {"day": datetime.date(2026, 11, 3)})
    assert value == {"day": "2026-11-03"}


# --- with Redis --------------------------------------------------------------

def test_a_second_read_is_answered_from_redis(redis_url, prefix):
    cache, _, _ = _cache(redis_url, prefix)
    load = _Loader({"rows": [1, 2, 3]})
    assert cache.read("t1", "stats", ("2026-11-01", "2026-11-07"), load) == {"rows": [1, 2, 3]}
    assert cache.read("t1", "stats", ("2026-11-01", "2026-11-07"), load) == {"rows": [1, 2, 3]}
    assert load.calls == 1


def test_different_arguments_are_different_reads(redis_url, prefix):
    cache, _, _ = _cache(redis_url, prefix)
    first, second = _Loader("boss"), _Loader("member")
    assert cache.read("t1", "overview", ("boss",), first) == "boss"
    assert cache.read("t1", "overview", ("member",), second) == "member"
    assert (first.calls, second.calls) == (1, 1)


def test_a_none_answer_is_cached_too(redis_url, prefix):
    cache, _, _ = _cache(redis_url, prefix)
    load = _Loader(None)
    assert cache.read("t1", "current", ("boss",), load) is None
    assert cache.read("t1", "current", ("boss",), load) is None
    assert load.calls == 1


def test_a_write_of_the_team_retires_its_reads_only(redis_url, prefix):
    cache, _, _ = _cache(redis_url, prefix)
    mine, theirs = _Loader("mine"), _Loader("theirs")
    cache.read("t1", "overview", (), mine)
    cache.read("t2", "overview", (), theirs)
    cache.written({"t1"})
    cache.read("t1", "overview", (), mine)
    cache.read("t2", "overview", (), theirs)
    assert (mine.calls, theirs.calls) == (2, 1)


def test_a_write_with_no_team_retires_every_team(redis_url, prefix):
    cache, _, _ = _cache(redis_url, prefix)
    loads = {team: _Loader(team) for team in ("t1", "t2")}
    for team, load in loads.items():
        cache.read(team, "overview", (), load)
    cache.written({""})
    for team, load in loads.items():
        cache.read(team, "overview", (), load)
    assert [load.calls for load in loads.values()] == [2, 2]


def test_another_process_s_write_is_seen(redis_url, prefix):
    api, _, _ = _cache(redis_url, prefix)
    worker, _, _ = _cache(redis_url, prefix)
    load = _Loader("board")
    api.read("t1", "period", ("s1",), load)
    worker.written({"t1"})
    api.read("t1", "period", ("s1",), load)
    assert load.calls == 2


def test_a_new_day_is_a_new_read(redis_url, prefix):
    store = _store(redis_url, prefix)
    hub = RedisHub(store)
    today = ["2026-11-03"]
    cache = ReadCache(hub, store, today=lambda: today[0])
    load = _Loader("x")
    cache.read("t1", "overview", (), load)
    today[0] = "2026-11-04"
    cache.read("t1", "overview", (), load)
    assert load.calls == 2


def test_every_key_starts_with_the_chosen_prefix(redis_url, prefix):
    cache, hub, _ = _cache(redis_url, prefix)
    cache.read("t1", "stats", ("a",), _Loader(1))
    cache.written({"t1"})
    cache.written({""})
    client = hub.client()
    ours = list(client.scan_iter(match=prefix + ":*"))
    assert ours, "nothing was written under the prefix"
    assert all(key.startswith(prefix + ":") for key in ours)
    report = probe(redis_url, prefix=prefix)
    assert report["app"]["prefix"] == prefix
    assert report["app"]["cached_reads"] == 1


def test_a_cached_read_expires_with_the_ttl(redis_url, prefix):
    cache, hub, _ = _cache(redis_url, prefix, ttl=60)
    cache.read("t1", "stats", (), _Loader(1))
    key = next(iter(hub.client().scan_iter(match=prefix + ":cache:read:*")))
    assert 0 < hub.client().ttl(key) <= 60


def test_a_ttl_of_zero_turns_the_cache_off(redis_url, prefix):
    cache, hub, _ = _cache(redis_url, prefix, ttl=0)
    load = _Loader(1)
    cache.read("t1", "stats", (), load)
    cache.read("t1", "stats", (), load)
    assert load.calls == 2
    assert not list(hub.client().scan_iter(match=prefix + ":cache:read:*"))


def test_a_write_that_missed_redis_is_paid_before_a_read_is_trusted(redis_url, prefix):
    cache, _, store = _cache(redis_url, prefix)
    load = _Loader("before")
    cache.read("t1", "overview", (), load)
    # Redis goes away for this process; a write happens meanwhile.
    store.settings.redis_url = "redis://127.0.0.1:1/0"
    cache.written({"t1"})
    store.settings.redis_url = redis_url
    load.value = "after"
    assert cache.read("t1", "overview", (), load) == "after"
    assert load.calls == 2


def test_a_password_in_the_url_is_never_shown():
    assert mask_url("redis://app:s3cret@cache:6379/0") == "redis://app:********@cache:6379/0"
    assert mask_url("redis://cache:6379/0") == "redis://cache:6379/0"


def test_an_evicted_generation_never_revives_an_old_read(redis_url, prefix):
    cache, hub, _ = _cache(redis_url, prefix)
    load = _Loader("old")
    cache.read("t1", "overview", (), load)
    cache.written({"t1"})
    # Redis drops the team's counter under memory pressure.
    for key in hub.client().scan_iter(match=prefix + ":cache:team:*"):
        hub.client().delete(key)
    load.value = "new"
    assert cache.read("t1", "overview", (), load) == "new"


def test_the_hub_never_polls_the_settings_from_inside_a_write():
    """`store.get()` may read the database (the shared settings); the hub
    runs inside a write's invalidation, so it reads what is held instead."""
    settings = _store("").settings

    class _Store:
        def get(self):
            raise AssertionError("polled the settings during invalidation")

        def peek(self):
            return settings

    hub = RedisHub(_Store())
    assert hub.client() is None
    assert hub.key("cache", "x") == "pakash:cache:x"
