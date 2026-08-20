"""Which model serves which kind of work.

Three roles, one server. Every role names a model id on the SAME
OpenAI-compatible endpoint (`llm_base_url`) — a role is a choice of *model*,
never a choice of connection, which is why the client keeps one shared
`OpenAI` instance and its connection pool across all of them. A vLLM server
started with several models answers for all of them on one port; addressing
another is a different `model` field on the request and nothing else.

Roles are resolved from the runtime settings store immediately before each
request, so a model changed in the settings panel applies to the next call
without restarting the backend — the same property `llm_model` already had.

An unset role falls back to `llm_model`. That is what keeps a deployment
serving one model working exactly as it did before roles existed: the
fallback is the whole of the backward-compatibility story, so it is one
`or` here rather than a condition spread over the call path.
"""

FAST = "fast"
DEFAULT = "default"
ADVANCED = "advanced"

# The runtime-settings field backing each role.
_ROLE_FIELDS = {
    FAST: "llm_model_fast",
    DEFAULT: "llm_model_default",
    ADVANCED: "llm_model_advanced",
}

# Flow → role. `flow` is the name every `bl/` caller already passes for
# telemetry, so routing rides on the argument that exists rather than adding
# a second one every call site would have to repeat and could disagree with.
#
# `scheduler` is the one advanced flow: it reasons over a whole period of
# slots, people and rules at once, and it is the call whose quality the
# product is actually judged on. `briefing` is fast because it is a few
# sentences over facts `bl/audit.py` already computed. Everything else is
# conversation-shaped and sits on the default.
_FLOW_ROLES = {
    "scheduler": ADVANCED,
    "interview": DEFAULT,
    "changes": DEFAULT,
    "planner": DEFAULT,
    "learn": DEFAULT,
    "briefing": FAST,
}


def role_for_flow(flow: str) -> str:
    """The role a flow runs on. An unmapped or missing flow gets DEFAULT —
    a new caller lands on the general-purpose model rather than silently
    borrowing the fast or advanced one."""
    return _FLOW_ROLES.get((flow or "").strip(), DEFAULT)


def resolve_model(settings, role: str, override: str = "") -> str:
    """The model id to send, resolved against the live settings.

    Order: an explicit override, then the role's configured model, then
    `llm_model`. `getattr` with a default rather than attribute access
    because a settings object predating these fields — a saved file from an
    older version, or a test double — must resolve, not raise.
    """
    if override:
        return override
    field = _ROLE_FIELDS.get(role or DEFAULT, _ROLE_FIELDS[DEFAULT])
    return getattr(settings, field, "") or settings.llm_model
