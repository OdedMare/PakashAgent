"""The live override store.

Settings saved in the UI beat env values WITHOUT a restart, because
`dal/llm/` reads this store on every call. Secrets are masked on the way out;
a masked value coming back means "unchanged", so the stored secret is kept.
"""

import json
from dataclasses import asdict, fields, replace
from pathlib import Path

from app.common.config import (
    Settings,
)
from app.common.runtime_settings.normalizers import (
    MASKED_SECRET,
    extract_url_schema,
    normalize_database_schema,
    normalize_database_url,
    normalize_llm_base_url,
    normalize_redis_host,
    normalize_redis_port,
    normalize_redis_prefix,
    normalize_redis_url,
)
from app.common.runtime_settings.runtime_settings import RuntimeSettings

_SECRET_FIELDS = {
    "database_password",
    "openai_api_key",
    "llm_api_key_fast",
    "llm_api_key_default",
    "llm_api_key_advanced",
    "redis_password",
}

# Fields where None/empty means "clear the value", not "keep current".
# Without this, an emptied base URL or port could never be unset from the UI.
_LLM_BASE_URL_FIELDS = (
    "llm_base_url",
    "llm_base_url_fast",
    "llm_base_url_default",
    "llm_base_url_advanced",
)
_NULLABLE = ("database_port", "redis_port", *_LLM_BASE_URL_FIELDS)

# Integers where 0 is not a meaningful value and is clamped away. Only
# concurrency qualifies: `llm_timeout_seconds` is handled separately because
# 0 there means "no timeout" and must survive.
#
# `llm_max_concurrency` is read by the shared PostgreSQL limiter on each
# acquisition, so the positive value saved here applies without a restart.
_POSITIVE_INTS = ("llm_max_concurrency", "solver_workers")


class RuntimeSettingsStore:
    def __init__(self, env: Settings):
        self._path = Path(env.runtime_settings_file)
        self._settings = RuntimeSettings(
            # Env values get the same normalization as UI edits, so a
            # jdbc: URL works however it is supplied.
            database_url=_safe_database_url(env.database_url),
            database_user=env.database_user,
            database_password=env.database_password,
            database_host=env.database_host,
            database_port=env.database_port,
            database_name=env.database_name,
            database_schema=_safe_schema(
                extract_url_schema(env.database_url) or env.database_schema
            ),
            llm_model=env.llm_model,
            llm_diet_mode=env.llm_diet_mode,
            llm_repetition_penalty=_clamp_penalty(env.llm_repetition_penalty),
            llm_timeout_seconds=env.llm_timeout_seconds,
            llm_max_concurrency=env.llm_max_concurrency,
            llm_base_url=env.llm_base_url,
            openai_api_key=env.openai_api_key,
            llm_model_fast=env.llm_model_fast,
            llm_model_default=env.llm_model_default,
            llm_model_advanced=env.llm_model_advanced,
            llm_base_url_fast=env.llm_base_url_fast,
            llm_base_url_default=env.llm_base_url_default,
            llm_base_url_advanced=env.llm_base_url_advanced,
            llm_api_key_fast=env.llm_api_key_fast,
            llm_api_key_default=env.llm_api_key_default,
            llm_api_key_advanced=env.llm_api_key_advanced,
            llm_queue_seconds=env.llm_queue_seconds,
            llm_verify_ssl=env.llm_verify_ssl,
            solver_time_limit_seconds=_seconds(env.solver_time_limit_seconds),
            solver_workers=max(1, int(env.solver_workers)),
            redis_url=_safe_redis_url(env.redis_url),
            redis_host=_safe(normalize_redis_host, env.redis_host, ""),
            redis_port=_safe(normalize_redis_port, env.redis_port, None),
            redis_username=(env.redis_username or "").strip(),
            redis_password=env.redis_password,
            redis_key_prefix=_safe_redis_prefix(env.redis_key_prefix),
        )
        self._mtime = None
        if self._path.exists():
            self._mtime = self._path.stat().st_mtime_ns
            self._apply(json.loads(self._path.read_text("utf-8")), False)

    def get(self) -> RuntimeSettings:
        return self._settings

    def public(self) -> dict:
        """The settings as the API may return them — secrets masked.

        Never returns a stored secret: the UI shows the mask and sends it
        back untouched when the boss did not retype it.
        """
        data = asdict(self._settings)
        for key in _SECRET_FIELDS:
            data[key] = MASKED_SECRET if data.get(key) else ""
        return data

    def update(self, patch: dict) -> RuntimeSettings:
        """Apply a UI save, all of it or none of it.

        `_apply` walks the patch key by key, so a bad value midway would
        otherwise leave the earlier keys live in memory while `_persist` never
        runs — the file on disk and the settings every caller reads would
        disagree until the next restart. Validating against a copy and
        swapping it in only on success keeps the two in step.
        """
        candidate = replace(self._settings)
        self._apply(patch, True, candidate)
        self._settings = candidate
        self._persist()
        return self._settings

    def reload_if_changed(self) -> bool:
        """Pick up a save another process wrote to the file. True if it did.

        Each process holds its own store, so a save in one API worker -- or
        anywhere, as seen from `app.worker` -- otherwise reaches the others
        only on restart. `RedisHub` calls this (throttled) so a Redis URL
        saved in the panel reaches every process within seconds. A file
        caught mid-write fails to parse and is simply read next time.
        """
        try:
            mtime = self._path.stat().st_mtime_ns
        except OSError:
            return False
        if mtime == self._mtime:
            return False
        try:
            patch = json.loads(self._path.read_text("utf-8"))
        except (OSError, ValueError):
            return False
        candidate = replace(self._settings)
        self._apply(patch, False, candidate)
        self._settings = candidate
        self._mtime = mtime
        return True

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(asdict(self._settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._mtime = self._path.stat().st_mtime_ns

    def _apply(self, patch: dict, strict: bool, target=None) -> None:
        """Fold a patch into `target` (the live settings by default).

        `strict` separates the two callers: a UI save must reject a bad value
        loudly, while a saved file from an older version must not stop the
        process from booting. `target` lets `update` validate against a copy,
        so a strict failure leaves the live settings untouched.
        """
        settings = self._settings if target is None else target
        known = {item.name for item in fields(RuntimeSettings)}
        for key, value in patch.items():
            # A masked secret means "unchanged" — keep what is stored.
            if key not in known or value == MASKED_SECRET:
                continue
            if key in _NULLABLE and (value is None or value == ""):
                setattr(settings, key, None)
                continue
            if value is None:
                continue
            try:
                value = _normalized(key, value, patch, settings)
            except (TypeError, ValueError):
                if strict:
                    raise
                continue
            setattr(settings, key, value)


def _normalized(key: str, value, patch: dict, settings):
    """One field's value as it will be stored. Raises on an unusable value."""
    if key == "database_url":
        # A pasted jdbc:...?currentSchema=x sets the schema too, unless the
        # patch names one explicitly.
        in_url = extract_url_schema(value)
        if in_url and not patch.get("database_schema"):
            settings.database_schema = normalize_database_schema(in_url)
        return normalize_database_url(value)
    if key == "database_schema":
        return normalize_database_schema(value)
    if key in _LLM_BASE_URL_FIELDS:
        return normalize_llm_base_url(value)
    if key == "llm_repetition_penalty":
        # Float, and 0 is meaningful ("do not send it").
        return _clamp_penalty(value)
    if key in ("llm_timeout_seconds", "llm_queue_seconds"):
        # 0 means "no timeout, wait as long as the server needs", so these
        # cannot join the max(1, ...) group below -- that would turn a request
        # for no limit into a one-second one. Negatives fold to 0.
        return max(0, int(value))
    if key in _POSITIVE_INTS:
        return max(1, int(value))
    if key == "llm_verify_ssl":
        return _flag(value)
    if key == "solver_time_limit_seconds":
        return _seconds(value)
    if key == "redis_url":
        return normalize_redis_url(value)
    if key == "redis_key_prefix":
        return normalize_redis_prefix(value)
    if key == "redis_host":
        return normalize_redis_host(value)
    if key == "redis_port":
        return normalize_redis_port(value)
    if key == "redis_username":
        return str(value).strip()
    return value


def _safe_database_url(value: str) -> str:
    """Normalize an env URL, but never fail startup on a bad one.

    Returning it unchanged lets the connection raise a real error naming the
    URL, which is clearer than a crash during settings construction.
    """
    try:
        return normalize_database_url(value)
    except (TypeError, ValueError):
        return value


def _clamp_penalty(value) -> float:
    """0 means "do not send the parameter at all" — the off switch, and the
    default, since OpenAI rejects the key outright. 2.0 is the top of the
    range the servers implementing it accept. Values between 0 and 1 reward
    repetition rather than penalizing it; unusual, but a legitimate ask, so
    they pass through rather than being floored to neutral."""
    return min(2.0, max(0.0, float(value)))


def _flag(value) -> bool:
    """A boolean as JSON or a form may spell it. `bool("false")` is True, and
    for the TLS switch that would turn verification off by accident."""
    if isinstance(value, bool):
        return value
    cleaned = str(value).strip().lower()
    if cleaned in ("true", "1", "yes", "on"):
        return True
    if cleaned in ("false", "0", "no", "off"):
        return False
    raise ValueError("expected true or false, got %r" % (value,))


def _seconds(value) -> float:
    """A solver time limit: positive, and never beyond ten minutes."""
    return min(600.0, max(0.5, float(value)))


def _safe_redis_url(value: str) -> str:
    """The env URL, or no Redis at all rather than a failed start-up."""
    try:
        return normalize_redis_url(value)
    except (TypeError, ValueError):
        return ""


def _safe(normalize, value, fallback):
    """An env value through `normalize`, or `fallback` rather than a failed
    start-up."""
    try:
        return normalize(value)
    except (TypeError, ValueError):
        return fallback


def _safe_redis_prefix(value: str) -> str:
    try:
        return normalize_redis_prefix(value)
    except (TypeError, ValueError):
        return normalize_redis_prefix("")


def _safe_schema(value: str) -> str:
    try:
        return normalize_database_schema(value)
    except (TypeError, ValueError):
        return ""
