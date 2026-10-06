"""Narrow a failed preview without dropping rules or switching models."""

from app.bl.scheduler.planning import split_dates
from app.bl.scheduler.quality import combine_metrics, quality
from app.bl.scheduler.request import SpanRequest
from app.bl.scheduler.slots import build_slots
from app.bl.scheduler.values import bounded


def generate_split(scheduler, profile, first, last, options, error):
    slots = build_slots(profile, first, last)
    dates = sorted({slot["slot_date"] for slot in slots})
    halves = split_dates(dates)
    if not halves:
        raise error
    committed = list(options.get("already_scheduled") or [])
    result = dict(slots=slots, assignments=[], notes=[], warnings=[], summary="")
    measured = dict(getattr(error, "generation_metrics", {}), split_count=1)
    summaries = []
    for half in halves:
        pins = [row for row in options.get("required_assignments") or [] if row["date"] in half]
        generated = scheduler.generate_span(profile, half[0], half[-1],
            **dict(options, required_assignments=pins, already_scheduled=committed))
        # Replace dates that were explicitly requested for regeneration.
        committed = [row for row in committed if row.get("date") not in half]
        committed.extend(generated["assignments"])
        result["assignments"].extend(generated["assignments"])
        result["notes"].extend(generated.get("notes") or [])
        summaries.append(generated.get("summary") or "")
        measured = combine_metrics(measured, generated["metrics"])
    request = SpanRequest(profile, first, last, slots, options.get("availability"),
                          options.get("already_scheduled"), options.get("required_assignments"))
    result["warnings"] = request.audit(committed)
    measured.update(date=first, through=last, accepted=len(result["assignments"]),
                    warnings=len(result["warnings"]), status="complete",
                    quality=quality(committed, request.audit_slots, profile, result["warnings"]))
    measured.pop("quality_before", None)  # The initial request produced no draft to score.
    result.update(metrics=measured, summary=bounded(" ".join(summaries)))
    return result
