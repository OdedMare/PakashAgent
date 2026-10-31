"""The manager-chat turns code answers without a model round.

Three shapes, tried in order: an absence (`bl/absence/`, read and planned in
code), a team question nobody is named in -- who works, who did the most,
who is away -- and a plain candidate lookup for one named person on one
day. Each either finishes the turn or leaves it untouched for the model loop.
"""

import logging

from app.bl.absence import AbsenceFastPath

_log = logging.getLogger("pakash.chat")
_NO_USAGE = dict(prompt_tokens=0, completion_tokens=0, total_tokens=0, model_rounds=0)


class ChatFastAnswers:
    def __init__(self, repository, context, tools, planner):
        self._repo = repository
        self._tools = tools
        self._absence = AbsenceFastPath(repository, context, planner)

    def handle(self, state) -> bool:
        return self._absence.handle(state) or self._team(state) or self._replacements(state)

    def _team(self, state) -> bool:
        return self._finish(state, self._tools.team_question(
            state.team_id, state.request, state.profile, state.payload["schedule"] or None,
        ))

    def _replacements(self, state) -> bool:
        return self._finish(state, self._tools.replacement_lookup(
            state.team_id, state.request, state.context,
            state.payload["schedule"] or None, state.profile,
        ))

    def _finish(self, state, found) -> bool:
        if not found:
            return False
        reply, output = found
        output["_usage"] = dict(_NO_USAGE)
        self._repo.finish_chat_turn(
            state.chat_id, state.message_id, reply, "complete", output,
        )
        _log.info("chat usage rounds=0 prompt=0 completion=0 total=0")
        return True
