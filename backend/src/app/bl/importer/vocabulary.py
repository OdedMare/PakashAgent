"""Matching header cells against the workplace's declared shifts (D9)."""

from typing import List, Optional

from app.bl.importer.cells import is_weekday, normalise, parse_date, parse_hours, text


class ShiftVocabulary:
    """The declared shifts, with their hours.

    Carries `start_time`/`end_time` as well as the name because a real sheet
    often heads its columns with hours rather than names, and the hours are
    what identifies the shift then.
    """

    def __init__(self, shifts: List[dict]):
        self._shifts = shifts

    @classmethod
    def from_profile(cls, profile: Optional[dict]) -> "ShiftVocabulary":
        found, seen = [], set()
        for shift in (profile or {}).get("shifts") or []:
            if isinstance(shift, dict):
                name = text(shift.get("name"))
                start, end = text(shift.get("start_time")), text(shift.get("end_time"))
            else:
                name, start, end = text(shift), "", ""
            if not name or name in seen:
                continue
            seen.add(name)
            found.append({"name": name, "start_time": start, "end_time": end})
        return cls(found)

    def __bool__(self) -> bool:
        return bool(self._shifts)

    def match(self, value: str) -> str:
        """A header cell read as a shift name.

        A match returns the declared spelling, so `בוקר `, `משמרת בוקר` or the
        shift's own hours all land on the one name the workplace uses.

        **An unmatched header is not discarded.** The file is a real schedule
        the workplace ran; a sheet naming a shift the interview never
        mentioned is describing something that genuinely happened. So the
        cell's own text is taken, and the confirm screen is where the manager
        reconciles it. Nothing is *invented*: a name is either the
        workplace's declared one or the one written in the manager's file.
        """
        if not normalise(value) or parse_date(value) or is_weekday(value):
            return ""
        return self.declared(value) or value.strip()

    def declared(self, value: str) -> str:
        """A header cell matched strictly against the declared vocabulary.

        The strict half of `match`, without its "take the sheet's own word"
        fallback. Callers that need to know whether a cell is *recognised*
        must use this one. A column headed `07:00-15:00` folds into the shift
        running those hours, or one shift would appear twice.
        """
        cleaned = normalise(value)
        if not cleaned or parse_date(value) or is_weekday(cleaned):
            return ""
        for shift in self._shifts:
            name = normalise(shift.get("name"))
            if name and (cleaned == name or name in cleaned):
                return shift.get("name")
        hours = parse_hours(cleaned)
        if not hours:
            return ""
        for shift in self._shifts:
            declared = parse_hours("%s-%s" % (
                shift.get("start_time") or "", shift.get("end_time") or "",
            ))
            if declared and declared == hours:
                return shift.get("name")
        return ""

    def mostly_shifts(self, row: List[str], dates: List[tuple]) -> bool:
        """Whether a row's data cells are shift names rather than people.

        Evidence of a second header line (Sample B's nested header). Tested
        against the **declared** names only: `match`'s fallback accepts any
        text, people's names included, and would classify every data row as
        a header.
        """
        if not self._shifts:
            return False
        filled = matched = 0
        for column, _iso in dates:
            if column >= len(row) or not row[column]:
                continue
            filled += 1
            matched += bool(self.declared(row[column]))
        return filled > 0 and matched == filled

