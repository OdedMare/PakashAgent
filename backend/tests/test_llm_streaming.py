"""The client reading an answer as it streams, and falling back without one."""

from tests.test_llm_client import _bad_request, _client, _Response


class _Delta:
    def __init__(self, content):
        self.content = content


class _Chunk:
    def __init__(self, content=None, usage=None):
        self.choices = [] if content is None else [type("Choice", (), {"delta": _Delta(content)})()]
        self.usage = usage


class _StreamUsage:
    prompt_tokens = 7
    completion_tokens = 3
    total_tokens = 10


def _stream(*pieces):
    return iter([_Chunk(piece) for piece in pieces] + [_Chunk(usage=_StreamUsage())])


def test_a_streamed_answer_reaches_the_caller_as_it_grows_and_parses_whole():
    llm, fake = _client([_stream('{"reply": "שלו', 'ם"}')])
    seen = []

    result = llm.complete_json("system", "user", schema={"type": "object"}, on_text=seen.append)

    assert seen == ['{"reply": "שלו', '{"reply": "שלום"}']
    assert result["reply"] == "שלום"
    assert result["_usage"]["total_tokens"] == 10
    assert fake.completions.calls[0]["stream"] is True


def test_a_refused_stream_retries_the_same_rung_and_is_not_asked_again():
    llm, fake = _client([_bad_request("stream_options unsupported"), _Response('{"ok": 1}'),
                         _Response('{"ok": 2}')])

    first = llm.complete_json("system", "user", schema={"type": "object"}, on_text=lambda text: None)
    second = llm.complete_json("system", "user", schema={"type": "object"}, on_text=lambda text: None)

    calls = fake.completions.calls
    assert (first["ok"], second["ok"]) == (1, 2)
    assert calls[0]["stream"] is True
    # The same structured rung, asked plainly; the ladder did not step down.
    assert calls[1]["response_format"] == calls[0]["response_format"]
    assert "stream" not in calls[1] and "stream" not in calls[2]


def test_without_a_reader_nothing_streams():
    llm, fake = _client([_Response('{"ok": true}')])

    llm.complete_json("system", "user")

    assert "stream" not in fake.completions.calls[0]
