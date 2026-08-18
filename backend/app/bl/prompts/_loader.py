"""Load prompt text from disk, resolve includes, and cache the result.

Prompts are product wording that gets tuned by reading it, so they live as
markdown beside the code rather than as Python string constants. The loader
is the only thing that knows they are files at all: callers ask for a name
and get a string.

Composition is an include line rather than `%s` interpolation, because the
shared fragments are shared *wording* and an include says where the text
comes from at the point it lands:

    <!-- include: shared/interview_method.md -->

Includes resolve relative to this directory, nest, and are cycle-checked. A
missing or self-referential include raises at load time — these strings are
what the model is told to do, so a silently empty prompt is far worse than a
crash on the first call.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional

_DIRECTORY = Path(__file__).parent
_SUFFIX = ".md"
_INCLUDE = re.compile(
    r"^[ \t]*<!--[ \t]*include:[ \t]*(?P<name>[^>]+?)[ \t]*-->[ \t]*$", re.M
)

# Read once: `load` sits inside every interview turn, hot enough that
# re-reading per call would be waste for text that cannot change while the
# process runs.
_cache: Dict[str, str] = {}


def load(name: str, reload: bool = False) -> str:
    """The composed prompt registered under `name`, without its extension.

    `reload` re-reads from disk, which is the point of having these as
    files: wording can be iterated without restarting the process.
    """
    if reload:
        _cache.pop(name, None)
    if name not in _cache:
        _cache[name] = _compose(name, [])
    return _cache[name]


def clear_cache() -> None:
    """Drop every cached prompt, so the next `load` reads from disk."""
    _cache.clear()


def _compose(name: str, stack: List[str]) -> str:
    if name in stack:
        raise ValueError("prompt include cycle: " + " -> ".join(stack + [name]))
    text = _read(name)
    return _INCLUDE.sub(
        lambda match: _compose(_normalized(match.group("name")), stack + [name]),
        text,
    ).strip()


def _read(name: str) -> str:
    path = _path(name)
    if path is None:
        raise FileNotFoundError(name + _SUFFIX)
    return path.read_text(encoding="utf-8")


def _path(name: str) -> Optional[Path]:
    """The file for `name`, or None when it escapes the prompts directory.

    Names are developer-supplied rather than user-supplied, so this is a
    guard against a typo climbing out of the package, not a security
    boundary.
    """
    candidate = (_DIRECTORY / (name + _SUFFIX)).resolve()
    try:
        candidate.relative_to(_DIRECTORY.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _normalized(name: str) -> str:
    """An include target as a load name: slashes kept, extension dropped."""
    name = name.strip()
    return name[: -len(_SUFFIX)] if name.endswith(_SUFFIX) else name
