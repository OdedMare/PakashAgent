"""LLM client: the degradation ladder, the parse retry, and the helpers.

Driven by a fake OpenAI client — no server, no network.
"""

import json

import httpx
import pytest
from openai import BadRequestError

from app.common.errors import AgentError
from app.dal.llm.json_response_parser import extract_json
from app.dal.llm.message_merger import merge_system_into_user
from app.dal.llm.model_id_extractor import extract_model_ids
from app.dal.llm.openai_client import OpenAIJsonClient, _budget_seconds


class _Settings:
    def __init__(self, **overrides):
        self.llm_model = "test-model"
        self.llm_model_fast = ""
        self.llm_model_default = ""
        self.llm_model_advanced = ""
        self.llm_base_url_fast = None
        self.llm_base_url_default = None
        self.llm_base_url_advanced = None
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
    llm, _ = _client([_Response("")])
    with pytest.raises(AgentError):
        llm.complete_json("sys", "usr")


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
    for flow in ("briefing", "interview", "scheduler"):
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
    """
    for timeout in (30, 120, 300, 600, 900):
        settings = _Settings(llm_timeout_seconds=timeout)
        for flow in ("scheduler", "interview", "changes", ""):
            assert _budget_seconds(settings, flow) > timeout, (timeout, flow)


def test_a_slow_model_widens_the_budget_with_it():
    """The setting a deployment reaches for actually moves the ceiling.

    Raising the timeout used to do nothing for the scheduler, whose budget
    was hardcoded below it.
    """
    slow = _budget_seconds(_Settings(llm_timeout_seconds=600), "scheduler")
    quick = _budget_seconds(_Settings(llm_timeout_seconds=120), "scheduler")
    assert slow > quick


def test_the_scheduler_keeps_the_tighter_budget():
    """Daily generation is checkpointed, so it should give up sooner than a
    conversational call and let the failed day be retried on its own."""
    settings = _Settings(llm_timeout_seconds=600)
    assert (
        _budget_seconds(settings, "scheduler")
        < _budget_seconds(settings, "interview")
    )


def test_a_settings_object_without_the_field_still_resolves():
    """A saved file from an older version, or a test double, must not raise."""
    assert _budget_seconds(object(), "scheduler") > 0
    assert _budget_seconds(object(), "interview") > 0
