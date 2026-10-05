import re

# What `RuntimeSettingsStore.public()` returns in place of a stored secret,
# and what the UI sends back for a secret the boss did not retype. Lives here
# rather than in the store so the HTTP boundary can recognize it without
# importing the settings stack.
MASKED_SECRET = "********"

_JDBC_PREFIX = re.compile(r"^jdbc:", re.IGNORECASE)
_PG_SCHEMES = ("postgresql://", "postgres://")

# A schema name is interpolated into SQL (SET search_path), so it must never
# accept arbitrary strings.
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# JDBC spells the schema `currentSchema`; libpq has no such keyword and
# rejects the whole URI. The equivalent is an `options` payload.
_CURRENT_SCHEMA_RE = re.compile(r"[?&]currentSchema=([^&]+)", re.IGNORECASE)


def normalize_http_url(value: str, field: str) -> str:
    cleaned = value.strip().rstrip("/")
    if not cleaned.lower().startswith(("http://", "https://")):
        raise ValueError(field + " must start with http:// or https://")
    return cleaned


def normalize_llm_base_url(url: str) -> str:
    """Accept a pasted endpoint, not just the base.

    Users copy the URL they see in a gateway's docs or in another client,
    which usually ends at the operation. The OpenAI SDK appends the path
    itself, so those suffixes must come off or every call 404s.
    """
    cleaned = _strip_suffixes(
        url, ("/chat/completions", "/completions", "/models")
    )
    return normalize_http_url(cleaned, "llm_base_url")


def normalize_database_url(value: str) -> str:
    cleaned = _JDBC_PREFIX.sub("", value.strip())
    if not cleaned.lower().startswith(_PG_SCHEMES):
        raise ValueError(
            "database_url must start with postgresql:// "
            "(jdbc:postgresql://... is accepted and converted automatically)"
        )
    return _translate_current_schema(cleaned)


def extract_url_schema(value: str) -> str:
    """The schema a JDBC-style URL asks for, or "" when it names none.

    Lets a pasted JDBC string set the schema without also filling the
    separate database_schema field.
    """
    match = _CURRENT_SCHEMA_RE.search(value or "")
    return match.group(1).strip() if match else ""


def normalize_database_schema(value: str) -> str:
    """Validate a schema name. Empty means "use the server default"."""
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if not _SCHEMA_RE.match(cleaned):
        raise ValueError(
            "database_schema must be a plain identifier like 'pakash'"
        )
    return cleaned


def _translate_current_schema(url: str) -> str:
    """Rewrite JDBC's `currentSchema=x` into libpq's `options=-csearch_path=x`.

    libpq rejects the unknown keyword outright, so a working JDBC connection
    string would otherwise fail to connect at all.
    """
    match = _CURRENT_SCHEMA_RE.search(url)
    if not match:
        return url
    schema = normalize_database_schema(match.group(1))
    stripped = _CURRENT_SCHEMA_RE.sub("", url, count=1)
    # Removing the first parameter can leave `&` where `?` belongs.
    stripped = re.sub(r"\?&", "?", stripped, count=1)
    separator = "&" if "?" in stripped else "?"
    return "%s%soptions=-csearch_path%%3D%s" % (stripped, separator, schema)


def _strip_suffixes(url: str, suffixes) -> str:
    cleaned = url.strip().rstrip("/")
    suffix = next(
        (item for item in suffixes if cleaned.lower().endswith(item)), None
    )
    return cleaned[:-len(suffix)] if suffix else cleaned
