# 3.11 is what pyproject requires. Every dependency ships a wheel for it on
# both amd64 and aarch64, so the image needs no compiler and no apt step --
# the 3.8.10 image this replaced needed both, on an EOL Debian.
FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

# One container runs both the API and the job worker: schedule builds (code
# and model alike), chat turns and setup compiles are queued in PostgreSQL
# and executed by worker threads inside this same process (app/main.py).
# Set PAKASH_EMBEDDED_WORKER=false only when a separate
# `python -m app.worker` container runs them instead.
ENV PAKASH_EMBEDDED_WORKER=true
# API processes (uvicorn reads WEB_CONCURRENCY as --workers). One by default,
# because with the embedded worker on every process would run its own job
# lanes. Raise it together with PAKASH_EMBEDDED_WORKER=false and a separate
# worker, as docker-compose.yml does. A key in PAKASH_SESSION_SECRET or the
# database is required with more than one (D39, session_key.py).
ENV WEB_CONCURRENCY=1

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
