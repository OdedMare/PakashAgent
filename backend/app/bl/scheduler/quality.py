"""Comparable generation measurements using the product's existing audit."""

from statistics import pstdev

from app.bl.audit import shift_stats


COUNTERS = (
    "duration_ms", "model_calls", "failed_calls", "prompt_chars", "schema_chars", "reply_chars",
    "prompt_tokens", "completion_tokens", "total_tokens", "split_count",
)


def combine_metrics(previous: dict, current: dict) -> dict:
    """Accumulate paid work while keeping the latest draft's quality."""
    result = dict(previous, **current)
    for key in COUNTERS:
        result[key] = previous.get(key, 0) + current.get(key, 0)
    return result


def quality(roster, slots, profile, warnings) -> dict:
    stats = shift_stats(roster, profile.get("shifts") or [],
                        profile.get("employees") or [], slots=slots,
                        warnings=warnings, profile=profile)
    loads = stats["by_employee"]
    return {
        "coverage": stats["coverage"],
        "unfilled_seats": stats["coverage"]["required"] - stats["coverage"]["assigned"],
        "warning_counts": stats["warning_counts"],
        "by_employee": loads,
        "hours_stddev": round(pstdev([row["hours"] for row in loads]), 2) if loads else 0,
        "shifts_stddev": round(pstdev([row["shifts"] for row in loads]), 2) if loads else 0,
    }


def warning_costs(warnings) -> dict:
    """Identity and magnitude, so a filled slot cannot buy a new rest violation."""
    costs = {}
    for item in warnings:
        details = item.get("details") or {}
        key = tuple(item.get(field) or "" for field in
                    ("code", "severity", "employee", "date", "shift"))
        key += tuple(details.get(field) for field in ("required_role", "year", "week"))
        if "required" in details:
            cost = abs(details["required"] - details.get("assigned", 0))
        elif "hours" in details:
            cost = details["hours"] - details["limit"]
        elif "rest_hours" in details:
            cost = details["minimum"] - details["rest_hours"]
        elif "days" in details:
            cost = details["days"] - details["limit"]
        else:
            cost = 1
        costs[key] = costs.get(key, 0) + cost
    return costs


def no_worse(before, after) -> bool:
    baseline, candidate = warning_costs(before), warning_costs(after)
    return all(cost <= baseline.get(key, 0) + 1e-6 for key, cost in candidate.items())
