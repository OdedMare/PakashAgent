"""Bound weekly requests by input size as well as staffing demand."""

import json

from app.bl.scheduler.request import SpanRequest

# A character budget, not a token estimate or a promise about model capacity.
# An oversized single day keeps every rule; output/context failures stay visible.
MAX_SPAN_INPUT_CHARS = 32000


def sized_chunks(profile, chunks, availability=None):
    result = []
    for chunk in chunks:
        by_date = {}
        for slot in chunk:
            by_date.setdefault(slot["slot_date"], []).append(slot)
        current = []
        # ponytail: at most seven dates per chunk; measure whole prompts rather
        # than maintain a second estimate that drifts from the request contract.
        for slots in by_date.values():
            proposed = current + slots
            if current and input_chars(profile, proposed, availability) > MAX_SPAN_INPUT_CHARS:
                result.append(current)
                current = []
            current.extend(slots)
        if current:
            result.append(current)
    return result


def input_chars(profile, slots, availability):
    request = SpanRequest(profile, slots[0]["slot_date"], slots[-1]["slot_date"],
                          slots, availability, [], [])
    return len(json.dumps(request.payload([], "", []), ensure_ascii=False)) + \
        len(json.dumps(request.schema, ensure_ascii=False))


def split_dates(dates):
    middle = len(dates) // 2
    return [dates[:middle], dates[middle:]] if middle else []
