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

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
