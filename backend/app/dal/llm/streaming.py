"""One completion read as a stream, so a caller can show text as it arrives.

The ladder still decides the request's shape; this only changes how the
answer travels. `stream_options.include_usage` asks for the token counts in
the last chunk — servers that ignore it leave the counts at zero, which is
what a server reporting no usage already looked like.

**A server that refuses streaming is not a server that refuses the rung.**
Some OpenAI-compatible servers answer `stream` or `stream_options` with a
400. That 400 must not advance the ladder — the structured output it would
step away from was never the problem — so the caller retries the same rung
without a stream (`openai_client`), and remembers per endpoint not to ask
again.
"""

from app.dal.llm.completion_retry import create_with_retry


class TextStream:
    """Where a caller wants the text as it arrives, and whether it can.

    `on_text` receives the whole text so far after every chunk that added to
    it; it must be cheap or throttle itself, since chunks arrive per token.
    `refused` is set once the endpoint turned a stream down, so the rest of
    the call (and the client, for later calls) stops asking.
    """

    def __init__(self, on_text):
        self.on_text = on_text
        self.refused = False


def stream_completion(client, model, kwargs, deadline, on_text):
    """`(content, usage)` of one streamed completion."""
    request = dict(kwargs, stream=True, stream_options={"include_usage": True})
    response = create_with_retry(client, model, request, deadline=deadline)
    text = ""
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for chunk in response:
        if getattr(chunk, "usage", None):
            usage = {
                "prompt_tokens": chunk.usage.prompt_tokens or 0,
                "completion_tokens": chunk.usage.completion_tokens or 0,
                "total_tokens": chunk.usage.total_tokens or 0,
            }
        for choice in getattr(chunk, "choices", None) or ():
            piece = getattr(choice.delta, "content", None)
            if piece:
                text += piece
                on_text(text)
    return text, usage
