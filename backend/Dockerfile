# 3.8.10 is what pyproject pins (mirroring AiSummryIO's deployment target),
# so the image matches it rather than quietly building on something newer —
# a wheel built here must run there.
FROM python:3.8.10-slim
WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
