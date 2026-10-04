"""One log line per logical model call: what it cost and how long it took."""

import logging
import time

from app.dal.llm.model_roles import DEFAULT

_log = logging.getLogger("pakash.llm")


def log_call(flow, model, usage, started, attempt, failed=False, role=""):
    """Counts and timings only -- never the prompt, the reply, or any part of
    either. Those carry employee names and stated reasons for absence.

    `role` sits beside `model`: the role says which setting was consulted,
    the model says what actually ran. `retries` is broken out because a call
    that silently took two attempts costs double.
    """
    _log.info(
        "llm flow=%s role=%s model=%s prompt=%d completion=%d total=%d "
        "retries=%d duration=%.1fs%s",
        flow or "unknown", role or DEFAULT, model,
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        usage.get("total_tokens", 0),
        attempt,
        time.monotonic() - started,
        " FAILED" if failed else "",
    )
