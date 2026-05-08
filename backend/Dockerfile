FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        zlib1g-dev libbz2-dev liblzma-dev && \
    rm -rf /var/lib/apt/lists/*
# Note: native build deps above are intentionally unpinned — they are
# pulled from the Debian snapshot bundled with the base image tag and
# are only needed at build time to compile the cyvcf2 C extension.
# Pin the base image digest in CI if fully reproducible builds are required.

COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt

COPY app/ ./app/

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
