# 3.11 is what pyproject requires. Every dependency ships a wheel for it on
# both amd64 and aarch64, so the image needs no compiler and no apt step --
# the 3.8.10 image this replaced needed both, on an EOL Debian.
FROM python:3.11-slim
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
