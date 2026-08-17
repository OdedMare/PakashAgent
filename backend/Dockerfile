# 3.8.10 is what pyproject pins (mirroring AiSummryIO's deployment target),
# so the image matches it rather than quietly building on something newer —
# a wheel built here must run there.
#
# The cost of that pin is visible in the next two blocks: this image is
# Debian buster, which is past EOL, so its apt mirrors have moved to
# archive.debian.org and its security suite no longer exists. If the boss
# ever confirms a newer deployment target, all of this collapses back to a
# one-line `pip install`.
FROM python:3.8.10-slim
WORKDIR /app

RUN printf '%s\n' \
      'deb http://archive.debian.org/debian buster main' \
      'deb http://archive.debian.org/debian buster-updates main' \
      > /etc/apt/sources.list \
    && printf 'Acquire::Check-Valid-Until "false";\n' \
      > /etc/apt/apt.conf.d/99no-check-valid-until

COPY pyproject.toml ./
COPY app ./app

# gcc is not optional on 3.8: `pydantic-settings` pulls `backports.zoneinfo`,
# which ships no aarch64 wheel for this interpreter and compiles from source.
# It is removed again in the same layer so the compiler does not ride along
# into the published image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && pip install --no-cache-dir . \
    && apt-get purge -y gcc libc6-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
