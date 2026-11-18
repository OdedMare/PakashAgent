"""One transactional gate for changes the manager already confirmed in UI."""

from typing import Callable, Optional

from app.common.change_plan import applying_plan, current_plan_id


def apply_confirmed_change(
    repository,
    team_id: str,
    *,
    source: str,
    body: dict,
    apply: Callable[[], object],
    message: str,
    reason: str = "",
    agent_reason: str = "",
    schedule_id: Optional[Callable[[object], str] | str] = None,
):
    """Persist, execute and receipt a confirmed change as one unit.

    Existing plan execution may call the same domain services (a chat profile
    plan calls ``ProfileService.update``, for example). In that case the
    outer plan remains the owner. The capability check keeps small test fakes
    compatible while production repositories always take the durable path.
    """
    if current_plan_id() or not hasattr(repository, "new_change_plan_approval"):
        return apply()

    with repository.new_change_plan_approval(team_id, body, source) as plan:
        with applying_plan(plan["id"]):
            result = apply()
            resolved_schedule_id = _schedule_id(schedule_id, result)
            repository.append_change(
                team_id,
                "%s_approved" % source,
                schedule_id=resolved_schedule_id or None,
                reason=(reason or "").strip(),
                agent_reason=(agent_reason or message).strip(),
            )
            repository.mark_change_plan_applied(
                plan["id"], team_id,
                {
                    "message": message,
                    "schedule_id": resolved_schedule_id,
                },
            )
    return result


def _schedule_id(value, result) -> str:
    if callable(value):
        return (value(result) or "").strip()
    return (value or "").strip()
