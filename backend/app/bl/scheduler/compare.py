"""Compare saved results for one shared set of scheduling inputs; no model call."""

import argparse
import json
from pathlib import Path

from app.bl.audit import audit
from app.bl.scheduler.availability import effective_availability
from app.bl.scheduler.quality import COUNTERS, combine_metrics, no_worse, quality
from app.bl.scheduler.slots import build_slots


def performance(result):
    if "performance" in result:
        return {key: result["performance"].get(key, 0) for key in COUNTERS}
    measured = result.get("metrics")
    if measured is None:
        measured = [row.get("metrics") or {} for row in
                    (result.get("generation") or {}).get("days") or []]
    if isinstance(measured, dict):
        measured = [measured]
    total = {}
    for item in measured or []:
        total = combine_metrics(total, item)
    return {key: total.get(key, 0) for key in COUNTERS}


def compare(data):
    profile, first, last = data["profile"], data["starts_on"], data["ends_on"]
    slots = build_slots(profile, first, last)
    availability = effective_availability(profile, data.get("availability"), first, last)
    reports, findings = {}, {}
    for name in ("baseline", "candidate"):
        result = data[name]
        if any(row.get("date", "") < first or row.get("date", "") > last
               for row in result["assignments"]):
            raise ValueError("Both saved results must cover the shared comparison period")
        warnings = audit(result["assignments"], profile.get("shifts") or [],
                         profile.get("employees") or [], availability=availability,
                         profile=profile, slots=slots)
        findings[name] = warnings
        reports[name] = dict(quality=quality(result["assignments"], slots, profile, warnings),
                             performance=performance(result))
    before, after = reports["baseline"], reports["candidate"]
    reports["delta"] = {key: after["performance"][key] - before["performance"][key]
                        for key in COUNTERS}
    reports["delta"].update({key: round(after["quality"][key] - before["quality"][key], 2)
                             for key in ("unfilled_seats", "hours_stddev", "shifts_stddev")})
    reports["checks_not_worse"] = no_worse(findings["baseline"], findings["candidate"])
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(compare(json.loads(args.snapshot.read_text(encoding="utf-8"))),
                          ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)


if __name__ == "__main__":
    main()
