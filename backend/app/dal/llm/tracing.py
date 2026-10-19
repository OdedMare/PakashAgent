"""Opik tracing for model calls -- on when `OPIK_API_KEY` is set, inert otherwise.

One trace per logical `complete_json`, named by its flow, with every HTTP
completion under it as an LLM span: the ladder's rungs, the parse retry, and
the transient-failure retries each show up as their own span, so a call that
silently cost three round-trips looks like one that did.

**Unlike `telemetry.py`, this records the full prompt and reply.** They carry
employee names and stated reasons for absence, and they leave this machine
for the configured Opik workspace. That is the point of it -- a trace without
the text cannot answer "why did the model say that" -- and the reason it is
off unless a key is configured.

Nothing here may fail a model call. A tracing error is logged and the call
runs untraced.
"""

import contextlib
import logging

_log = logging.getLogger("pakash.llm")

_state = {"enabled": False, "project": ""}


def init(settings) -> bool:
    """Connect the process to Opik if `settings.opik_api_key` is set.

    Called once from each composition root (`main.py`, `worker.py`). The key,
    workspace and project come from `Settings`, so they may live in `.env`
    beside the rest of the configuration rather than only in the process
    environment Opik itself reads.
    """
    if not settings.opik_api_key:
        return False
    try:
        import opik

        opik.set_global_client(opik.Opik(
            api_key=settings.opik_api_key,
            workspace=settings.opik_workspace or None,
            project_name=settings.opik_project_name,
            host=settings.opik_url or None,
        ))
    except Exception:
        _log.exception("opik tracing disabled: client setup failed")
        return False
    _state.update(enabled=True, project=settings.opik_project_name)
    _log.info("opik tracing enabled project=%s", settings.opik_project_name)
    return True


def enabled() -> bool:
    return _state["enabled"]


def wrap(client):
    """The OpenAI client with every completion recorded as an LLM span."""
    if not enabled():
        return client
    try:
        from opik.integrations.openai import track_openai

        return track_openai(client, project_name=_state["project"])
    except Exception:
        _log.exception("opik could not wrap the OpenAI client")
        return client


@contextlib.contextmanager
def call(flow: str, role: str, model: str):
    """One trace around one logical model call. A call that raises closes
    its trace with the error attached."""
    with contextlib.ExitStack() as stack:
        if enabled():
            try:
                import opik

                stack.enter_context(opik.start_as_current_trace(
                    name=flow or "unknown",
                    tags=[flow or "unknown", role],
                    metadata={"flow": flow, "role": role, "model": model},
                    project_name=_state["project"],
                ))
            except Exception:
                _log.exception("opik could not open a trace flow=%s", flow)
        yield


def flush() -> None:
    """Send whatever is still batched. Called on shutdown."""
    if not enabled():
        return
    try:
        import opik

        opik.flush_tracker()
    except Exception:
        _log.exception("opik flush failed")
