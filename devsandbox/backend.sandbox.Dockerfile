# Sandbox backend image.
#
# Differs from backend/Dockerfile in three ways, all of them about being a
# throwaway development stack rather than a deliverable:
#
#   - dev dependencies are installed, so pytest runs inside the container
#   - the source is installed editable, so a bind mount can shadow it
#   - it runs as an unprivileged `app` user that owns /data, because the
#     Settings panel writes runtime-settings.json onto a named volume
#
# Build context is the repository root, so `backend/` is visible.

FROM python:3.8.10-slim

WORKDIR /srv/backend

# Same story as the production image: this base is Debian buster, which is
# end-of-life, so its packages have moved to archive.debian.org and the
# mirrors baked into the image serve no Release file. Repointing apt at the
# archive is what makes the toolchain installable. Signatures are still
# verified against the keyring already in the image; only the "valid until"
# date is ignored, since the archive's Release file is frozen in the past.
#
# gcc stays in this image rather than being purged in the same layer: the
# sandbox is rebuilt often, and `backports.zoneinfo` (a Python 3.8-only
# transitive dependency with no wheel for this platform) compiles from
# source every time.
RUN printf '%s\n' \
        'deb http://archive.debian.org/debian buster main' \
        > /etc/apt/sources.list \
    && apt-get update -o Acquire::Check-Valid-Until=false \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# uid/gid 999 matches the chown the `settings-permissions` service performs
# on the settings volume; they must be changed together.
RUN pip install --no-cache-dir --upgrade "pip<25" \
    && groupadd --system --gid 999 app \
    && useradd --system --uid 999 --gid app --home /srv/backend app

COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/tests ./tests

RUN pip install --no-cache-dir -e ".[dev]" \
    && chown -R app:app /srv/backend

USER app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
