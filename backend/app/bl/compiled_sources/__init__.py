"""Standing sources translated once and kept, so a build need not ask again (D32).

A rule, a policy, an employee's note or a preference says the same thing
next week as this week, so what the translating agent made of it is kept,
keyed on the words, the roster and the compiler. The setup form's save
queues the translation in the background; a build loads what is there and
translates only what is not. Nothing here calls a model or holds SQL.

| Module | Owns |
|---|---|
| `keys.py` | What a kept translation is keyed on: roster and shift names, compiler version |
| `timing.py` | Code's check on the model's reading of time ("חולה 3 או 4 ימים") |
| `shape.py` | An outcome as a stored row and back, re-checked against today's roster |
| `cache.py` | `TranslationCache`, one team's port onto the rows; `NullCache` keeps nothing |
| `compiler.py` | `SourceCompiler`: what the worker runs after setup is saved; `queue` |
| `report.py` | What code made of each standing source, for the setup screen |
"""

from app.bl.compiled_sources.cache import NullCache, TranslationCache
from app.bl.compiled_sources.compiler import SourceCompiler, queue
from app.bl.compiled_sources.report import report
from app.bl.compiled_sources.keys import COMPILER_VERSION, compiler_id, vocab_key
from app.bl.compiled_sources.timing import settle

__all__ = [
    "COMPILER_VERSION", "NullCache", "SourceCompiler", "TranslationCache", "compiler_id",
    "queue", "report", "settle", "vocab_key",
]
