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

FROM python:3.11-slim

WORKDIR /srv/backend

# uid/gid 999 matches the chown the `settings-permissions` service performs
# on the settings volume; they must be changed together.
RUN pip install --no-cache-dir --upgrade pip \
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
