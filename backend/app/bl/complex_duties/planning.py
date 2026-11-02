"""The fair fill and the balance, on top of `ComplexDutyService`.

`suggest` writes nothing: it reads the מכלול once (`ledger.py`) and hands
the pure `fill.suggest` everything it needs. `approve` seats what the
commander kept, one row at a time through the ordinary `assign` -- every
check, log line and notice a hand-set duty gets -- and reports each row it
could not seat beside the ones it did, rather than failing the batch on
the first: a seat taken in between is a row to say, not a reason to drop
the other twenty.
"""

import datetime
from typing import List

from app.bl.complex_duties import fill, values
from app.bl.complex_duties.balance import balance
from app.bl.complex_duties.ledger import DutyLedger
from app.common.errors import AgentError, AppError

# The most rows one approval seats.
MAX_APPROVE = 400


class DutyPlanning:
    def __init__(self, repository, complexes, duties):
        self._repository = repository
        self._complexes = complexes
        self._duties = duties

    def suggest(self, complex_id: str, start: str, end: str) -> dict:
        first, last = values.span(start, end)
        ledger = DutyLedger(self._repository, self._complexes, complex_id, first, last)
        types = [row for row in self._repository.complex_duty_types(complex_id) if row["active"]]
        result = fill.suggest(
            types, _dates(first, last), ledger.soldiers, ledger.duties,
            ledger.shift_days, ledger.ruled_out, ledger.busy_days,
        )
        result.update(start=first.isoformat(), end=last.isoformat(),
                      window_start=ledger.since.isoformat())
        return result

    def approve(self, complex_id: str, rows: List[dict]) -> dict:
        if len(rows) > MAX_APPROVE:
            raise AgentError("יותר מדי שיבוצים בבת אחת")
        saved, conflicts, failed = [], [], []
        for row in rows:
            try:
                result = self._duties.assign(
                    complex_id, row["duty_type_id"], row["team_id"], row["employee"],
                    row["duty_date"], row.get("note") or "", resolve=False,
                )
            except AppError as exc:
                failed.append(dict(row, error=str(exc)))
                continue
            saved.append(result["duty"])
            conflicts += result["conflicts"]
        if conflicts:
            # Once for the whole fill: one rebuild per week, not per row.
            conflicts = self._duties.resolve(complex_id, conflicts)
        return {"saved": saved, "conflicts": conflicts, "failed": failed}

    def balance(self, complex_id: str, start: str, end: str) -> dict:
        first, last = values.span(start, end)
        ledger = DutyLedger(self._repository, self._complexes, complex_id, first, last,
                            window_days=0)
        return balance(ledger, self._repository.complex_duty_types(complex_id), first, last)


def _dates(first: datetime.date, last: datetime.date) -> List[datetime.date]:
    return [first + datetime.timedelta(days=offset) for offset in range((last - first).days + 1)]
