"""Re-answer only problematic dates, then judge the entire fixed period."""

from app.bl.scheduler.request import SpanRequest
from app.bl.scheduler.values import bounded, lines


def repair_request(span, first, history, instructions, preferences):
    dates = {bounded(item.get("date")) for item in first.warnings + first.rejected}
    # A malformed row with no recognizable slot/date cannot be scoped safely.
    if "" in dates:
        dates = span.dates
    dates &= span.dates
    if not dates:
        dates = span.dates
    slots = [slot for slot in span.slots if slot["slot_date"] in dates]
    request = SpanRequest(span.profile, min(dates), max(dates), slots,
                          span.raw_availability, first.roster,
                          [row for row in span.required if row["date"] in dates])
    payload = request.payload(history, instructions, preferences)
    payload["repair"] = {
        "rejected_rows": first.rejected,
        "warnings": [item["message"] for item in first.warnings],
        "instruction": "החזר את כל השיבוצים לימים שבתקופה הזו בלבד. "
                       "תקן את הבעיות ואל תשנה שיבוצים בימים אחרים.",
    }
    return request, payload


def repaired_attempt(span, request, answer, first):
    second = request.read(answer)
    # Notes about untouched dates remain; notes for repaired dates stay visible too.
    second.answer = dict(answer, notes=list(dict.fromkeys(
        lines(first.answer.get("notes")) + lines(answer.get("notes")))))
    second.warnings = span.audit(second.roster)
    return second
