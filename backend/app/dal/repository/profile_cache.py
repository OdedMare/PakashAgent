"""The last profile read per team, keyed by the revision that wrote it.

`team_profile()` is read from dozens of places -- every tool a chat turn
runs, every build, every audit -- and the profile is the largest document a
team has. Every save bumps `revision` and stamps `updated_at`, so a read that
finds both unchanged can skip sending the document at all: the query still
runs, still sees the committed row, and only the transfer is saved.

Nothing read inside `atomic()` is kept (`TeamRepository.team_profile`):
a save there may yet roll back, and the next real save would reuse its
revision number. The pair is the key, not `revision` alone, so a write that
changed the document without bumping it -- hand-run SQL, a restored backup
-- is still noticed by its `updated_at`.

What is cached is the document's text. Every read parses its own copy, so a
caller that edits the dict it was handed cannot change what the next one gets.
"""

import threading
from collections import OrderedDict
from typing import Optional, Tuple

# Teams per process whose profile text is kept. Past it the least recently
# read is dropped and simply transferred again next time.
MAX_TEAMS = 256


class ProfileCache:
    def __init__(self, size: int = MAX_TEAMS):
        self._size = size
        self._entries: "OrderedDict[tuple, Tuple[object, object, str]]" = OrderedDict()
        self._lock = threading.Lock()

    def version(self, key: tuple) -> Tuple[object, object]:
        """The (revision, updated_at) held for `key`; (None, None) if none."""
        with self._lock:
            entry = self._entries.get(key)
        return (entry[0], entry[1]) if entry else (None, None)

    def text(self, key: tuple, revision, updated_at) -> Optional[str]:
        """The held text, only if it was written by exactly that version."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[:2] != (revision, updated_at):
                return None
            self._entries.move_to_end(key)
            return entry[2]

    def keep(self, key: tuple, revision, updated_at, text: str) -> None:
        with self._lock:
            self._entries[key] = (revision, updated_at, text)
            self._entries.move_to_end(key)
            while len(self._entries) > self._size:
                self._entries.popitem(last=False)

    def drop(self, key: tuple) -> None:
        with self._lock:
            self._entries.pop(key, None)
