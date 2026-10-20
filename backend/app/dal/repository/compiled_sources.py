"""Kept translations of standing sources, and the day each was first seen (D32)."""

from typing import Dict, List

from psycopg.types.json import Jsonb

from app.dal.database import connect
from app.dal.repository.base import RepositoryBase

_COLUMNS = ("source_key", "kind", "context", "text", "binding", "status", "translation",
            "reason", "expires_on", "question", "tokens", "anchored_on")


class CompiledSourcesRepository(RepositoryBase):
    def compiled_sources(self, team_id: str, vocab_key: str, compiler: str,
                         source_keys: List[str]) -> List[dict]:
        if not source_keys:
            return []
        rows = self._all("""
            SELECT * FROM compiled_sources
            WHERE team_id=%s AND vocab_key=%s AND compiler=%s AND source_key = ANY(%s)
        """, (team_id, vocab_key, compiler, list(source_keys)))
        return [_iso(row) for row in rows]

    def save_compiled_sources(self, team_id: str, vocab_key: str, compiler: str,
                              rows: List[dict]) -> None:
        with connect(self._store) as connection:
            for row in rows:
                values = [Jsonb(row[key]) if key == "translation" else row.get(key)
                          for key in _COLUMNS]
                connection.execute("""
                    INSERT INTO compiled_sources (team_id, vocab_key, compiler, %s)
                    VALUES (%%s, %%s, %%s, %s)
                    ON CONFLICT (team_id, source_key, vocab_key, compiler) DO UPDATE SET
                        %s, last_used_at=NOW()
                """ % (", ".join(_COLUMNS), ", ".join(["%s"] * len(_COLUMNS)),
                       ", ".join("%s=EXCLUDED.%s" % (key, key) for key in _COLUMNS[1:])),
                    [team_id, vocab_key, compiler] + values)
            connection.commit()

    def touch_compiled_sources(self, team_id: str, source_keys: List[str]) -> None:
        self._execute("""
            UPDATE compiled_sources SET last_used_at=NOW()
            WHERE team_id=%s AND source_key = ANY(%s)
        """, (team_id, list(source_keys)))

    def prune_compiled_sources(self, team_id: str, days: int = 90) -> None:
        """Translations no build has used for `days`: an old roster's, an old prompt's."""
        self._execute("""
            DELETE FROM compiled_sources
            WHERE team_id=%s AND last_used_at < NOW() - make_interval(days => %s)
        """, (team_id, int(days)))

    def source_anchors(self, team_id: str, source_keys: List[str], today: str) -> Dict[str, str]:
        """Each key's first-seen day, recording `today` for keys never seen."""
        if not source_keys:
            return {}
        with connect(self._store) as connection:
            for key in source_keys:
                connection.execute("""
                    INSERT INTO source_anchors (team_id, source_key, anchored_on)
                    VALUES (%s,%s,%s) ON CONFLICT (team_id, source_key) DO NOTHING
                """, (team_id, key, today))
            rows = connection.execute("""
                SELECT source_key, anchored_on FROM source_anchors
                WHERE team_id=%s AND source_key = ANY(%s)
            """, (team_id, list(source_keys))).fetchall()
            connection.commit()
        return {row["source_key"]: row["anchored_on"].isoformat() for row in rows}


def _iso(row: dict) -> dict:
    for key in ("expires_on", "anchored_on"):
        if row.get(key) is not None and hasattr(row[key], "isoformat"):
            row[key] = row[key].isoformat()
    return row


__all__ = ["CompiledSourcesRepository"]
