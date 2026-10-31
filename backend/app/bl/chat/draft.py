"""The reply as the model writes it, shown before the turn finishes.

The model answers in JSON, and `reply` is the schema's first field, so its
text arrives first. `partial_reply` reads it out of a JSON object that is
still being written; `ReplyDraft` saves it on the working message a few times
a second. The draft is only ever shown on a `working` message: the finished
turn's content replaces it, and nothing reads a draft as an answer.
"""

import logging
import time

_log = logging.getLogger("pakash.chat")
_KEY = '"reply"'
_EVERY_SECONDS = 0.35
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f"}


def partial_reply(text):
    """The `reply` string of a possibly unfinished JSON object, decoded as
    far as it goes; empty until the string has started."""
    start = text.find(_KEY)
    if start < 0:
        return ""
    index = start + len(_KEY)
    while index < len(text) and text[index] in " \t\r\n:":
        index += 1
    if index >= len(text) or text[index] != '"':
        return ""
    index += 1
    out = []
    while index < len(text) and text[index] != '"':
        char = text[index]
        if char != "\\":
            out.append(char)
            index += 1
            continue
        if index + 1 >= len(text):
            break
        escaped = text[index + 1]
        if escaped == "u":
            if index + 6 > len(text):
                break
            try:
                out.append(chr(int(text[index + 2:index + 6], 16)))
            except ValueError:
                break
            index += 6
            continue
        out.append(_ESCAPES.get(escaped, escaped))
        index += 2
    return "".join(out)


class ReplyDraft:
    """Throttled writes of the reply so far. A failed write is logged and
    dropped: the draft is a courtesy, and the turn must not die for it."""

    def __init__(self, write, clock=time.monotonic):
        self._write = write
        self._clock = clock
        self._sent = ""
        self._at = None

    def __call__(self, text):
        now = self._clock()
        if self._at is not None and now - self._at < _EVERY_SECONDS:
            return
        draft = partial_reply(text).strip()
        if not draft or draft == self._sent:
            return
        self._sent, self._at = draft, now
        try:
            self._write(draft)
        except Exception:  # noqa: BLE001 -- the answer still arrives whole
            _log.warning("chat draft write failed", exc_info=True)
