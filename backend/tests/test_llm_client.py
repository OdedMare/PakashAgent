"""LLM client: the degradation ladder, the parse retry, and the helpers.

Driven by a fake OpenAI client — no server, no network.
"""

import json

import httpx
import pytest
from openai import BadRequestError

from app.common.errors import AgentError, ModelOutputError
from app.dal.llm.json_response_parser import extract_json
from app.dal.llm.message_merger import merge_system_into_user
from app.dal.llm.model_id_extractor import extract_model_ids
from app.dal.llm.openai_client import (
    OpenAIJsonClient,
    _budget_seconds,
    read_timeout_for,
)


class _Settings:
    def __init__(self, **overrides):
        self.llm_model = "test-model"
        self.llm_model_fast = ""
        self.llm_model_default = ""
        self.llm_model_advanced = ""
        self.llm_base_url_fast = None
        self.llm_base_url_default = None
        self.llm_base_url_advanced = None
        self.llm_api_key_fast = ""
        self.llm_api_key_default = ""
        self.llm_api_key_advanced = ""
        self.llm_diet_mode = False
        self.llm_repetition_penalty = 0.0
        self.llm_timeout_seconds = 120
        self.llm_base_url = "http://localhost:11434/v1"
        self.openai_api_key = ""
        for key, value in overrides.items():
            setattr(self, key, value)


class _Store:
    def __init__(self, settings):
        self._settings = settings

    def get(self):
        return self._settings


class _Usage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15


class _Response:
    def __init__(self, content, usage=True):
        message = type("Message", (), {"content": content})()
        self.choices = [type("Choice", (), {"message": message})()]
        self.usage = _Usage() if usage else None


def _bad_request(message="unsupported"):
    request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError(message, response=response, body=None)


class _FakeCompletions:
    """Records every request and replies from a scripted queue.

    A callable in the queue is raised or returned as the script decides.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.models = []

    def create(self, model, temperature, **kwargs):
        self.calls.append(kwargs)
        self.models.append(model)
        item = self.script.pop(0) if self.script else _Response('{"ok": true}')
        if isinstance(item, Exception):
            raise item
        return item


class _FakeClient:
    def __init__(self, script):
        self.completions = _FakeCompletions(script)
        self.chat = type("Chat", (), {"completions": self.completions})()


def _client(script, settings=None, monkeypatch=None):
    llm = OpenAIJsonClient(_Store(settings or _Settings()))
    fake = _FakeClient(script)
    # Bypass the real OpenAI constructor and the connection cache.
    llm._client_for = lambda *args, **kwargs: fake
    return llm, fake


# --- the degradation ladder ------------------------------------------------

def test_schema_is_the_first_rung_when_one_is_given():
    llm, fake = _client([_Response('{"ok": true}')])
    llm.complete_json("sys", "usr", schema={"type": "object"})
    assert fake.completions.calls[0]["response_format"]["type"] == "json_schema"


def test_json_mode_is_the_first_rung_without_a_schema():
    llm, fake = _client([_Response('{"ok": true}')])
    llm.complete_json("sys", "usr")
    assert fake.completions.calls[0]["response_format"]["type"] == "json_object"


def test_backend_time_context_is_injected_into_every_model_request(monkeypatch):
    monkeypatch.setattr(
        "app.dal.llm.openai_client.agent_time_context",
        lambda: "CURRENT ISRAEL CLOCK",
    )
    llm, fake = _client([_Response('{"ok": true}')])

    llm.complete_json("original system prompt", "usr")

    system, user = fake.completions.calls[0]["messages"]
    # The clock ends the prompt, so a minute ticking past leaves the system
    # prompt and the user's context a reusable prefix.
    assert system == {"role": "system", "content": "original system prompt"}
    assert user == {"role": "user", "content": "usr\n\nCURRENT ISRAEL CLOCK"}


def test_ladder_steps_down_through_every_rung_on_bad_request():
    # schema → json_object → plain → merged system prompt
    llm, fake = _client([
        _bad_request(), _bad_request(), _bad_request(),
        _Response('{"ok": true}'),
    ])
    result = llm.complete_json("sys", "usr", schema={"type": "object"})

    assert result["ok"] is True
    formats = [call.get("response_format") for call in fake.completions.calls]
    assert formats[0]["type"] == "json_schema"
    assert formats[1]["type"] == "json_object"
    assert formats[2] is None
    # The last rung carries no system role at all.
    last = fake.completions.calls[3]["messages"]
    assert [item["role"] for item in last] == ["user"]
    assert "sys" in last[0]["content"]


def test_the_next_call_starts_from_the_rung_that_answered():
    # A server that refused json_schema once refuses it every time; paying
    # that 400 again on each call is a wasted round-trip.
    llm, fake = _client([_bad_request(), _Response('{"ok": 1}'), _Response('{"ok": 2}')])
    llm.complete_json("sys", "usr", schema={"type": "object"})
    llm.complete_json("sys", "usr", schema={"type": "object"})

    formats = [call["response_format"]["type"] for call in fake.completions.calls]
    assert formats == ["json_schema", "json_object", "json_object"]


def test_a_remembered_rung_belongs_to_one_schema():
    llm, fake = _client([_bad_request(), _Response('{"ok": 1}'), _Response('{"ok": 2}')])
    llm.complete_json("sys", "usr", schema={"type": "object"})
    llm.complete_json("sys", "usr", schema={"type": "object", "required": ["ok"]})

    assert fake.completions.calls[2]["response_format"]["type"] == "json_schema"


def test_a_remembered_rung_still_steps_down_when_it_is_refused():
    llm, fake = _client([
        _bad_request(), _Response('{"ok": 1}'),
        _bad_request(), _Response('{"ok": 2}'), _Response('{"ok": 3}'),
    ])
    for _ in range(3):
        llm.complete_json("sys", "usr", schema={"type": "object"})

    formats = [(call.get("response_format") or {}).get("type") for call in fake.completions.calls]
    assert formats == ["json_schema", "json_object", "json_object", None, None]


def test_a_caller_can_pin_the_clock_for_a_series_of_calls():
    llm, fake = _client([_Response('{"ok": 1}'), _Response('{"ok": 2}')])
    llm.complete_json("sys", "usr", time_context="PINNED CLOCK")
    llm.complete_json("sys", "usr", time_context="PINNED CLOCK")

    users = [call["messages"][1]["content"] for call in fake.completions.calls]
    assert users == ["usr\n\nPINNED CLOCK"] * 2


def test_a_non_bad_request_error_does_not_advance_the_ladder():
    # Only a 400 means "the server rejected this shape". Anything else is a
    # real failure and must surface immediately rather than being retried
    # three more times against the same broken server.
    llm, fake = _client([RuntimeError("connection reset")])
    with pytest.raises(AgentError):
        llm.complete_json("sys", "usr")
    assert len(fake.completions.calls) == 1


def test_every_rung_failing_raises_agent_error():
    llm, _ = _client([_bad_request() for _ in range(4)])
    with pytest.raises(AgentError):
        llm.complete_json("sys", "usr")


# --- the parse retry -------------------------------------------------------

def test_a_non_json_reply_is_retried_with_the_error_appended():
    llm, fake = _client([_Response("sorry, no"), _Response('{"ok": true}')])
    assert llm.complete_json("sys", "usr")["ok"] is True

    second = fake.completions.calls[1]["messages"]
    roles = [item["role"] for item in second]
    assert roles == ["system", "user", "assistant", "user"]
    assert "not valid JSON" in second[-1]["content"]


def test_two_invalid_replies_raise_agent_error():
    llm, fake = _client([_Response("nope"), _Response("still nope")])
    with pytest.raises(AgentError):
        llm.complete_json("sys", "usr")
    assert len(fake.completions.calls) == 2


def test_an_empty_reply_is_an_error_not_an_empty_object():
    llm, _ = _client([_Response(""), _Response("")])
    with pytest.raises(AgentError):
        llm.complete_json("sys", "usr")


def test_an_empty_reply_is_retried_and_its_tokens_still_counted():
    # gpt-oss answers with a native function call and no content; it was paid for.
    llm, fake = _client([_Response(None), _Response('{"ok": true}')])
    result = llm.complete_json("sys", "usr")
    assert result["ok"] is True
    assert result["_usage"]["total_tokens"] == 30
    assert "Do not call functions" in fake.completions.calls[1]["messages"][-1]["content"]


def test_two_empty_replies_raise_with_the_tokens_they_spent():
    llm, _ = _client([_Response(""), _Response("")])
    with pytest.raises(ModelOutputError) as raised:
        llm.complete_json("sys", "usr")
    assert raised.value.usage["total_tokens"] == 30


# --- usage, diet mode, penalty --------------------------------------------

def test_usage_is_reported_when_the_server_provides_it():
    llm, _ = _client([_Response('{"ok": true}')])
    assert llm.complete_json("sys", "usr")["_usage"]["total_tokens"] == 15


def test_usage_is_omitted_when_the_server_reports_none():
    llm, _ = _client([_Response('{"ok": true}', usage=False)])
    assert "_usage" not in llm.complete_json("sys", "usr")


def test_usage_accumulates_across_a_parse_retry():
    # Tokens spent on the rejected reply were still spent.
    llm, _ = _client([_Response("nope"), _Response('{"ok": true}')])
    assert llm.complete_json("sys", "usr")["_usage"]["total_tokens"] == 30


def test_diet_mode_bounds_the_completion():
    llm, fake = _client(
        [_Response('{"ok": true}')], _Settings(llm_diet_mode=True)
    )
    llm.complete_json("sys", "usr")
    assert fake.completions.calls[0]["max_tokens"] == 1200


def test_no_max_tokens_is_sent_when_diet_mode_is_off():
    llm, fake = _client([_Response('{"ok": true}')])
    llm.complete_json("sys", "usr")
    assert "max_tokens" not in fake.completions.calls[0]


def test_neutral_repetition_penalty_is_never_sent():
    # OpenAI 400s on the unknown key, and that 400 is indistinguishable from
    # the ones the ladder exists to step around.
    llm, fake = _client([_Response('{"ok": true}')])
    llm.complete_json("sys", "usr")
    assert "extra_body" not in fake.completions.calls[0]


def test_a_set_repetition_penalty_travels_in_extra_body():
    llm, fake = _client(
        [_Response('{"ok": true}')], _Settings(llm_repetition_penalty=1.1)
    )
    llm.complete_json("sys", "usr")
    assert fake.completions.calls[0]["extra_body"] == {
        "repetition_penalty": 1.1
    }


# --- local-server accommodations ------------------------------------------

def test_no_api_key_is_required_when_a_base_url_is_set():
    llm, _ = _client([_Response('{"ok": true}')], _Settings(openai_api_key=""))
    assert llm.complete_json("sys", "usr")["ok"] is True


def test_neither_key_nor_base_url_is_a_hebrew_configuration_error():
    llm, _ = _client(
        [], _Settings(openai_api_key="", llm_base_url=None)
    )
    with pytest.raises(AgentError) as caught:
        llm.complete_json("sys", "usr")
    assert "API" in str(caught.value)


def test_client_setup_failure_is_an_agent_error_not_a_500():
    llm, _ = _client([])
    llm._client_for = lambda *args, **kwargs: (_ for _ in ()).throw(
        ValueError("invalid provider URL")
    )

    with pytest.raises(AgentError) as caught:
        llm.complete_json("sys", "usr", flow="planner")

    assert "חיבור למודל" in str(caught.value)


# --- helpers ---------------------------------------------------------------

def test_extract_json_strips_a_markdown_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_finds_an_object_inside_prose():
    assert extract_json('Here you go: {"a": 1} — hope that helps') == {"a": 1}


def test_extract_json_rejects_a_bare_array():
    # Callers index the result by key; a list would fail later and further away.
    with pytest.raises(json.JSONDecodeError):
        extract_json("[1, 2, 3]")


def test_extract_json_keeps_hebrew_intact():
    assert extract_json('{"shift": "בוקר"}')["shift"] == "בוקר"


def test_merge_system_into_user_folds_the_system_turn():
    merged = merge_system_into_user([
        {"role": "system", "content": "S"},
        {"role": "user", "content": "U"},
    ])
    assert merged == [{"role": "user", "content": "S\n\nU"}]


def test_merge_leaves_messages_without_a_system_turn_alone():
    messages = [{"role": "user", "content": "U"}]
    assert merge_system_into_user(messages) == messages


@pytest.mark.parametrize("payload", [
    {"data": [{"id": "b"}, {"id": "a"}]},
    {"models": [{"name": "b"}, {"name": "a"}]},
    ["b", "a"],
])
def test_model_ids_are_read_from_every_envelope_servers_use(payload):
    assert extract_model_ids(payload) == ["a", "b"]


def test_model_ids_of_an_unexpected_payload_is_empty_not_an_error():
    assert extract_model_ids({"unexpected": True}) == []


# --- context overflow is not a shape rejection -----------------------------

def _overflow(message):
    """A 400 of the kind a server returns for a prompt past its context."""
    request = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    response = httpx.Response(400, request=request)
    return BadRequestError(message, response=response, body=None)


def test_context_overflow_stops_the_ladder_instead_of_walking_it():
    """Every rung sends the same oversized messages, so stepping down cannot
    help — it only buries the real cause behind whichever rung ran last."""
    llm, fake = _client([
        _overflow("This model's maximum context length is 8192 tokens"),
        _Response('{"ok": true}'),
    ])
    with pytest.raises(AgentError) as error:
        llm.complete_json("sys", "usr", schema={"type": "object"})
    assert "חלון ההקשר" in str(error.value)
    # Stopped on the first rung rather than trying all four.
    assert len(fake.completions.calls) == 1


def test_a_shape_rejection_still_advances_the_ladder():
    llm, fake = _client([_bad_request("response_format is unsupported")])
    assert llm.complete_json("sys", "usr", schema={"type": "object"})["ok"]
    assert len(fake.completions.calls) == 2


@pytest.mark.parametrize("message", [
    "maximum context length is 4096",
    "Requested tokens exceed context window",
    "input is too long for this model",
    "n_ctx is too small",
])
def test_the_overflow_markers_the_local_servers_actually_use(message):
    llm, _ = _client([_overflow(message)])
    with pytest.raises(AgentError) as error:
        llm.complete_json("sys", "usr")
    assert "חלון ההקשר" in str(error.value)


# --- task-based model routing ----------------------------------------------

def test_the_flow_picks_the_model_the_request_actually_sends():
    settings = _Settings(
        llm_model_advanced="big-model", llm_model_fast="small-model",
    )
    llm, fake = _client([_Response('{"ok": true}')], settings)
    llm.complete_json("sys", "usr", flow="scheduler")
    assert fake.completions.models == ["big-model"]


def test_the_briefing_runs_on_the_fast_model():
    settings = _Settings(
        llm_model_advanced="big-model", llm_model_fast="small-model",
    )
    llm, fake = _client([_Response('{"ok": true}')], settings)
    llm.complete_json("sys", "usr", flow="briefing")
    assert fake.completions.models == ["small-model"]


def test_an_unset_role_sends_the_existing_default_model():
    # The backward-compatibility path: nothing configured, nothing changes.
    llm, fake = _client([_Response('{"ok": true}')], _Settings())
    llm.complete_json("sys", "usr", flow="scheduler")
    assert fake.completions.models == ["test-model"]


def test_an_explicit_model_argument_wins_over_the_flow():
    settings = _Settings(llm_model_advanced="big-model")
    llm, fake = _client([_Response('{"ok": true}')], settings)
    llm.complete_json("sys", "usr", flow="scheduler", model="pinned")
    assert fake.completions.models == ["pinned"]


def test_a_model_saved_mid_session_applies_to_the_next_call():
    # Resolved from the store per call, so a settings save needs no restart.
    settings = _Settings()
    llm, fake = _client([
        _Response('{"ok": true}'), _Response('{"ok": true}'),
    ], settings)
    llm.complete_json("sys", "usr", flow="scheduler")
    settings.llm_model_advanced = "big-model"
    llm.complete_json("sys", "usr", flow="scheduler")
    assert fake.completions.models == ["test-model", "big-model"]


def test_every_role_uses_its_configured_endpoint():
    settings = _Settings(
        llm_model_fast="small-model",
        llm_model_default="chat-model",
        llm_model_advanced="big-model",
        llm_base_url_fast="http://fast/v1",
        llm_base_url_default="http://chat/v1",
        llm_base_url_advanced="http://advanced/v1",
    )
    llm = OpenAIJsonClient(_Store(settings))
    fake = _FakeClient([_Response('{"ok": true}')] * 3)
    built = []

    def record(api_key, base_url, timeout):
        built.append((api_key, base_url, timeout))
        return fake

    llm._client_for = record
    for flow in ("briefing", "changes", "scheduler"):
        llm.complete_json("sys", "usr", flow=flow)

    assert fake.completions.models == ["small-model", "chat-model", "big-model"]
    assert [call[1] for call in built] == [
        "http://fast/v1", "http://chat/v1", "http://advanced/v1",
    ]


def test_unset_role_endpoints_keep_using_the_general_endpoint():
    settings = _Settings(
        llm_model_fast="small-model",
        llm_model_advanced="big-model",
    )
    llm = OpenAIJsonClient(_Store(settings))
    fake = _FakeClient([_Response('{"ok": true}')] * 2)
    built = []

    def record(api_key, base_url, timeout):
        built.append(base_url)
        return fake

    llm._client_for = record
    llm.complete_json("sys", "usr", flow="briefing")
    llm.complete_json("sys", "usr", flow="scheduler")

    assert built == ["http://localhost:11434/v1"] * 2


def test_every_role_sends_its_own_api_key_to_its_own_endpoint():
    """Roles on different providers need different credentials, and each one
    must reach only the endpoint it belongs to."""
    settings = _Settings(
        llm_base_url_fast="http://fast/v1",
        llm_base_url_advanced="https://api.provider.com/v1",
        llm_api_key_advanced="sk-advanced",
        openai_api_key="general-key",
    )
    llm = OpenAIJsonClient(_Store(settings))
    fake = _FakeClient([_Response('{"ok": true}')] * 3)
    built = []

    def record(api_key, base_url, timeout):
        built.append((api_key, base_url))
        return fake

    llm._client_for = record
    for flow in ("briefing", "changes", "scheduler"):
        llm.complete_json("sys", "usr", flow=flow)

    assert built == [
        # Its own endpoint, but no key of its own — a local server needs none.
        ("general-key", "http://fast/v1"),
        ("general-key", "http://localhost:11434/v1"),
        ("sk-advanced", "https://api.provider.com/v1"),
    ]


def test_a_role_key_and_url_are_cached_as_one_connection():
    """The client cache is keyed by (key, URL, timeout), so two roles on the
    same endpoint with different keys never share a pool — one of them would
    otherwise authenticate as the other."""
    settings = _Settings(
        llm_base_url_fast="https://api.provider.com/v1",
        llm_base_url_advanced="https://api.provider.com/v1",
        llm_api_key_fast="sk-one",
        llm_api_key_advanced="sk-two",
    )
    llm = OpenAIJsonClient(_Store(settings))

    fast = llm._client_for(*_connection(settings, "fast"))
    advanced = llm._client_for(*_connection(settings, "advanced"))

    assert fast is not advanced


def _connection(settings, role):
    from app.dal.llm.model_roles import resolve_api_key, resolve_base_url
    return resolve_api_key(settings, role), resolve_base_url(settings, role), 0


def test_a_role_key_is_enough_when_no_general_key_is_set():
    """A deployment whose only credential belongs to one role must not be
    told it has no API key configured."""
    settings = _Settings(
        openai_api_key="",
        llm_base_url=None,
        llm_base_url_advanced="https://api.provider.com/v1",
        llm_api_key_advanced="sk-advanced",
    )
    llm = OpenAIJsonClient(_Store(settings))
    fake = _FakeClient([_Response('{"ok": true}')])
    llm._client_for = lambda api_key, base_url, timeout: fake

    assert llm.complete_json("sys", "usr", flow="scheduler")["ok"] is True


def test_the_ladder_still_runs_per_call_on_the_routed_model():
    # Routing must not disturb the degradation ladder: every rung is the same
    # model, and a rejected rung does not switch to another one.
    settings = _Settings(llm_model_advanced="big-model")
    llm, fake = _client([
        _bad_request(), _bad_request(), _bad_request(),
        _Response('{"ok": true}'),
    ], settings)
    llm.complete_json("sys", "usr", schema={"type": "object"}, flow="scheduler")
    assert fake.completions.models == ["big-model"] * 4


def test_a_failing_model_is_never_swapped_for_another_one():
    """No automatic failover. Retrying a timed-out generation on a second
    model can duplicate work that the first one is still finishing."""
    settings = _Settings(llm_model_advanced="big-model")
    llm, fake = _client([
        _Response("not json"), _Response("still not json"),
    ], settings)
    with pytest.raises(AgentError):
        llm.complete_json("sys", "usr", flow="scheduler")
    # Both attempts, including the parse retry, stayed on the routed model.
    assert set(fake.completions.models) == {"big-model"}


# -- the total-call budget -------------------------------------------------
#
# These lock the invariant, not the numbers. What matters is that the ceiling
# on a whole logical call always leaves room for at least one HTTP round-trip
# — when it did not, the deadline expired before any attempt could finish and
# the retries and the ladder became unreachable.


def test_the_budget_always_leaves_room_for_one_round_trip():
    """The invariant that makes the retry and the ladder reachable at all.

    Both used to be flat constants, so raising `llm_timeout_seconds` past the
    scheduler's fixed 120s inverted them: one HTTP call could no longer finish
    inside the budget bounding it.

    The scheduler is excluded because it no longer has a round trip to leave
    room for -- its read is unbounded, so there is no ceiling to fit inside.
    """
    for timeout in (30, 120, 300, 600, 900):
        settings = _Settings(llm_timeout_seconds=timeout)
        for flow in ("planner", "changes", ""):
            assert _budget_seconds(settings, flow) > timeout, (timeout, flow)


def test_no_timeout_still_ends_a_stuck_chat_call():
    """0 used to mean "wait forever", and one chat call the server never
    answered then held its worker and model slot until a restart: every later
    message sat on "ממתין למודל…". It now means the built-in ceiling."""
    for timeout in (0, -30):
        settings = _Settings(llm_timeout_seconds=timeout)
        for flow in ("changes", "planner", ""):
            ceiling = read_timeout_for(settings, flow)
            assert ceiling == 300, (timeout, flow)
            assert _budget_seconds(settings, flow) > ceiling, (timeout, flow)


def test_the_default_ceiling_leaves_room_for_the_ladder():
    """End to end: with the default timeout the ladder runs every rung it needs.

    Guards the wiring, not the arithmetic — a budget of 0 seconds would have
    stopped this after the first BadRequestError.
    """
    settings = _Settings(llm_timeout_seconds=0)
    llm, fake = _client([
        _bad_request(), _bad_request(), _Response('{"ok": true}'),
    ], settings)
    assert llm.complete_json(
        "sys", "usr", schema={"type": "object"}, flow="scheduler",
    )["ok"] is True
    assert len(fake.completions.models) == 3


def test_a_slow_model_widens_the_budget_with_it():
    """The setting a deployment reaches for actually moves the ceiling.

    Raising the timeout used to do nothing, because the budget was hardcoded
    below it.
    """
    slow = _budget_seconds(_Settings(llm_timeout_seconds=600), "changes")
    quick = _budget_seconds(_Settings(llm_timeout_seconds=120), "changes")
    assert slow > quick


def test_building_a_schedule_is_never_cut_off_by_the_timeout():
    """The failure this replaced, seen in production.

    `llm_timeout_seconds` is one number for calls that are not comparable: a
    briefing is a short prompt to the fast model, one day of scheduling is a
    large prompt to the heavy model. A value that keeps the settings panel
    responsive is, for the scheduler, a ceiling below the real answer time --
    so the briefing kept working while every build died on `ReadTimeout` with
    the model server still generating. So the scheduler's ceiling is its own,
    far above any answer time, and its budget leaves room for that attempt.
    """
    for timeout in (30, 120, 600, 900):
        settings = _Settings(llm_timeout_seconds=timeout)
        ceiling = read_timeout_for(settings, "scheduler")
        assert ceiling >= 900 and ceiling >= timeout, timeout
        assert _budget_seconds(settings, "scheduler") > ceiling, timeout
        # Every other flow still honours the manager's setting exactly.
        assert read_timeout_for(settings, "changes") == timeout, timeout


def test_a_build_the_server_never_answers_still_ends():
    """One unanswered call used to hold the model slot forever: with the
    default limit of one, every chat and every build queued behind it. The
    scheduler's read is bounded even when the setting says "no timeout"."""
    for timeout in (0, -30):
        settings = _Settings(llm_timeout_seconds=timeout)
        assert read_timeout_for(settings, "scheduler") > 0, timeout
        assert _budget_seconds(settings, "scheduler") is not None, timeout


def test_the_scheduler_client_is_built_with_its_own_ceiling():
    """The wiring, not the arithmetic: `complete_json` must hand the flow's
    own ceiling to the client, or the decision above never reaches httpx."""
    built = []
    settings = _Settings(llm_timeout_seconds=120)
    llm, _ = _client([_Response('{"ok": true}')], settings)

    original = llm._client_for

    def record(api_key, base_url, timeout):
        built.append(timeout)
        return original(api_key, base_url, timeout)

    llm._client_for = record
    llm.complete_json("sys", "usr", flow="scheduler")
    llm.complete_json("sys", "usr", flow="briefing")

    assert built == [read_timeout_for(settings, "scheduler"), 120]


def test_a_settings_object_without_the_field_still_resolves():
    """A saved file from an older version, or a test double, must not raise.

    It resolves to the default ceiling, which is the same answer an explicit
    0 gets.
    """
    assert read_timeout_for(object(), "changes") == 300
    assert _budget_seconds(object(), "changes") > 300


def test_ssl_verification_is_on_unless_turned_off(monkeypatch):
    """Off, the SDK is handed an httpx client that accepts any certificate;
    flipping the switch builds a new client rather than reusing the old."""
    import app.dal.llm.openai_client as module

    built = []
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: built.append(kwargs) or object())
    settings = _Settings()
    llm = OpenAIJsonClient(_Store(settings))

    llm._client_for("", "http://local/v1", 0)
    settings.llm_verify_ssl = False
    llm._client_for("", "http://local/v1", 0)

    assert "http_client" not in built[0]
    assert "http_client" in built[1]


def test_the_models_probe_honours_the_ssl_switch(monkeypatch):
    import app.dal.llm.openai_client as module

    seen = []

    class _Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"id": "m"}]}

    monkeypatch.setattr(
        module.httpx, "get",
        lambda url, **kwargs: seen.append(kwargs["verify"]) or _Reply(),
    )
    settings = _Settings(llm_verify_ssl=False)
    llm = OpenAIJsonClient(_Store(settings))

    llm.list_models()
    llm.list_models(verify_ssl_override=True)

    assert seen == [False, True]


# --- the server tripping over its own output, and how long it thinks -------

_HARMONY = "unexpected tokens remaining in message header: Some(\"<|start|>assistant\")"


def test_a_harmony_glitch_asks_the_same_rung_again():
    """gpt-oss on vLLM 400s when its sampled text breaks its own format.
    Stepping down the ladder would only drop the structured output."""
    llm, fake = _client([_bad_request(_HARMONY), _Response('{"ok": true}')])
    assert llm.complete_json("sys", "usr", schema={"type": "object"})["ok"] is True
    first, second = fake.completions.calls
    assert first["response_format"] == second["response_format"]


def test_a_harmony_glitch_that_persists_still_steps_down():
    llm, fake = _client([_bad_request(_HARMONY)] * 3 + [_Response('{"ok": true}')])
    assert llm.complete_json("sys", "usr")["ok"] is True
    formats = [call.get("response_format") for call in fake.completions.calls]
    assert formats[:3] == [{"type": "json_object"}] * 3
    assert formats[3] is None


def test_reasoning_effort_is_sent_only_when_set():
    llm, fake = _client([_Response('{"ok": true}')])
    llm.complete_json("sys", "usr")
    assert "reasoning_effort" not in fake.completions.calls[0]
    assert "extra_body" not in fake.completions.calls[0]


@pytest.mark.parametrize("effort, sent", [("off", "low"), ("low", "low"), ("high", "high")])
def test_gpt_oss_gets_reasoning_effort(effort, sent):
    settings = _Settings(llm_model="gpt-oss-120b", llm_reasoning_effort=effort)
    llm, fake = _client([_Response('{"ok": true}')], settings)
    llm.complete_json("sys", "usr")
    assert fake.completions.calls[0]["reasoning_effort"] == sent


@pytest.mark.parametrize("effort, thinking", [("off", False), ("low", False), ("medium", True)])
def test_qwen_gets_its_chat_template_switch(effort, thinking):
    settings = _Settings(
        llm_model="qwen3.5-35b-a3b", llm_reasoning_effort=effort,
        llm_repetition_penalty=1.1,
    )
    llm, fake = _client([_Response('{"ok": true}')], settings)
    llm.complete_json("sys", "usr")
    call = fake.completions.calls[0]
    assert "reasoning_effort" not in call
    assert call["extra_body"] == {
        "repetition_penalty": 1.1,
        "chat_template_kwargs": {"enable_thinking": thinking},
    }
