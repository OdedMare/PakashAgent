"""Guessing a sheet's layout in code, by reading it every plausible way.

No template and no class per shape: each plausible `Layout` -- both
orientations, each line that could be the header, with and without a
shift line under it, each meaning a lane could have -- is read by the one
reader and scored by how much of the sheet it explains *in this
workplace's own terms*: cells that resolve to people on the roster, on
shifts the profile declares. Sideways Sample A, people down the side with
shift names in the cells, a weekly template of weekday names -- all of them
are a layout, and none needed code of its own.
"""

from typing import List, Optional, Tuple

from app.bl.importer.headers import MAX_HEADER_SCAN, carried, header_dates
from app.bl.importer.layout import DATES_ACROSS, DATES_DOWN, LANES, Layout, orient
from app.bl.importer.reader import Reading, read
from app.bl.importer.roster import AMBIGUOUS, EXACT, MATCHED, match_people
from app.bl.importer.vocabulary import ShiftVocabulary
from app.common.errors import AgentError

# Headers tried per orientation: the lines with the most dates.
_HEADERS_TRIED = 3

Scored = Tuple[float, float, Reading]


def detect(grid: List[List[str]], profile: Optional[dict],
           vocabulary: ShiftVocabulary, week_start: str = "") -> List[Scored]:
    """Every reading that explained anything, best first, as
    `(score, confidence, reading)`."""
    found, seen = [], set()
    for layout in _layouts(grid, vocabulary, week_start):
        if layout.key() in seen:
            continue
        seen.add(layout.key())
        try:
            reading = read(grid, layout, vocabulary, week_start)
        except AgentError:
            continue
        score, confidence = evaluate(reading, profile, vocabulary)
        if score > 0:
            found.append((score, confidence, reading))
    return sorted(found, key=lambda item: item[0], reverse=True)


def evaluate(reading: Reading, profile: Optional[dict],
             vocabulary: ShiftVocabulary) -> Tuple[float, float]:
    """`(score, confidence)`: how much it explains and how sure it reads.

    A row counts in full when its person is on the roster and its shift is
    declared, and less for each part the workplace does not know. With no
    roster to compare against, a name is only half evidence -- any word is
    a name until something says otherwise.
    """
    rows = reading.assignments
    if not rows and not reading.unavailability:
        return 0.0, 0.0
    people = match_people([row["employee"] for row in rows], profile)
    has_roster = bool((profile or {}).get("employees"))
    total = 0.0
    for row in rows:
        total += _person_weight(people.get(row["employee"]), has_roster) \
            * _shift_weight(row["shift"], vocabulary)
    total += 0.4 * sum(1 for row in reading.unavailability if row["employee"]) \
        + 0.15 * sum(1 for row in reading.unavailability if not row["employee"])
    unexplained = max(0, reading.filled - reading.explained)
    score = max(0.0, total - 0.5 * unexplained)
    # Out of what this reading could have scored had every name and shift
    # been the workplace's own: a sheet that is mostly "בית" is no less sure.
    ideal = len(rows) + 0.4 * len(reading.unavailability) + 0.5 * unexplained
    confidence = score / max(1.0, ideal)
    return score, round(min(1.0, confidence), 2)


def _person_weight(match: Optional[dict], has_roster: bool) -> float:
    if not has_roster:
        return 0.6
    status = (match or {}).get("status")
    if status in (EXACT, MATCHED):
        return 1.0
    return 0.45 if status == AMBIGUOUS else 0.2


def _shift_weight(shift: str, vocabulary: ShiftVocabulary) -> float:
    if not shift:
        return 0.35
    if not vocabulary:
        return 0.8
    return 1.0 if vocabulary.declared(shift) else 0.4


def _layouts(grid, vocabulary: ShiftVocabulary, week_start: str):
    for orientation in (DATES_ACROSS, DATES_DOWN):
        oriented = orient(grid, orientation)
        for header in _headers(oriented, week_start):
            for shift_line in _shift_lines(oriented, header, vocabulary, week_start):
                for lanes in LANES:
                    yield Layout(orientation=orientation, header=header,
                                 shift_line=shift_line, lanes=lanes)


def _headers(grid, week_start: str) -> List[int]:
    counted = []
    for index, row in enumerate(grid[:MAX_HEADER_SCAN]):
        dates, _assumed = header_dates(row, week_start)
        if dates:
            counted.append((len(dates), index))
    counted.sort(key=lambda item: (-item[0], item[1]))
    return [index for _count, index in counted[:_HEADERS_TRIED]]


def _shift_lines(grid, header: int, vocabulary: ShiftVocabulary,
                 week_start: str) -> List[Optional[int]]:
    """No shift line, and the line under the header when it reads as one:
    two or more shift names under a single date (Sample B's nested header),
    skipping a weekday line in between."""
    found: List[Optional[int]] = [None]
    dates, _assumed = header_dates(grid[header], week_start)
    for line in (header + 1, header + 2):
        if line >= len(grid):
            break
        by_column = carried(dates, len(grid[line]))
        per_date = {}
        for column, value in enumerate(grid[line]):
            if column in by_column and vocabulary.match(value):
                per_date[by_column[column]] = per_date.get(by_column[column], 0) + 1
        if per_date and max(per_date.values()) >= 2:
            found.append(line)
            break
    return found
