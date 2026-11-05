"""Chat adapter for the source-independent change-plan service."""

from app.bl.change_plans import ChangePlanService


class ChatPlanApplier:
    def __init__(self, repository, schedules, context, profiles=None):
        self._repo = repository
        self._plans = ChangePlanService(
            repository, schedules, context, profiles,
        )

    def apply(
        self, team_id, manager_id, chat_id, message_id,
        accept_exceptions=False, confirmation=None,
    ):
        plan_id = self._repo.ensure_chat_change_plan(
            team_id, manager_id, chat_id, message_id,
        )
        source = {}

        def guard(_stored):
            source["message"] = self._repo.lock_chat_plan_source(
                team_id, manager_id, chat_id, message_id, plan_id,
            )

        def applied(receipt):
            payload = dict(source["message"].get("payload") or {})
            payload["plan_id"] = plan_id
            payload["receipt"] = receipt
            self._repo.mark_chat_applied(chat_id, message_id, payload)
            if confirmation:
                self._repo.record_chat_confirmation(
                    chat_id, confirmation["content"],
                    confirmation["request_id"], receipt,
                )

        chat = self._repo.get_chat(team_id, manager_id, chat_id)
        message = next(row for row in chat["messages"] if row["id"] == message_id)
        self._plans.approve(
            team_id, plan_id, accept_exceptions=accept_exceptions,
            request_text=message["content"], source_guard=guard,
            on_applied=applied,
        )
        return self._repo.get_chat(team_id, manager_id, chat_id)
