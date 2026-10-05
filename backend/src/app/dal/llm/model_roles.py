"""Which model, endpoint and credential serve each kind of work.

Every role may name a model id, an OpenAI-compatible base URL, and the API
key for that URL. An unset role field falls back to the general
`llm_model` / `llm_base_url` / `openai_api_key` trio, so one-server
deployments need no changes.

The key is per role for the same reason the URL is: a role pointing at
another provider is authenticated by another credential. Once
`llm_base_url_advanced` names a hosted API while the general endpoint is a
local Ollama, one shared key is necessarily wrong for one of them — either
absent where it is required, or sent to a server it does not belong to.

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

_ROLE_URL_FIELDS = {
    FAST: "llm_base_url_fast",
    DEFAULT: "llm_base_url_default",
    ADVANCED: "llm_base_url_advanced",
}

_ROLE_KEY_FIELDS = {
    FAST: "llm_api_key_fast",
    DEFAULT: "llm_api_key_default",
    ADVANCED: "llm_api_key_advanced",
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


def resolve_base_url(settings, role: str):
    """The role endpoint, falling back to the existing shared endpoint."""
    field = _ROLE_URL_FIELDS.get(role or DEFAULT, _ROLE_URL_FIELDS[DEFAULT])
    return getattr(settings, field, None) or settings.llm_base_url


def resolve_api_key(settings, role: str) -> str:
    """The credential for this role's endpoint.

    Falls back to `openai_api_key`, which is what keeps a deployment whose
    roles all sit on one server working with the single key it always had.

    **The fallback is on the key alone, not on the pair.** A role naming its
    own URL but no key still borrows the general key — a second Ollama on
    the LAN needs the placeholder, not a credential — and the client sends
    the placeholder when both are empty, so a local endpoint is never
    blocked for want of a key it ignores.
    """
    field = _ROLE_KEY_FIELDS.get(role or DEFAULT, _ROLE_KEY_FIELDS[DEFAULT])
    return getattr(settings, field, "") or settings.openai_api_key
