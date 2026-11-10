# Temporary Quack record server for the dev stack (docker/compose-dev-services.yaml).
# No records in the image: the compose service mounts them at /srv/data/records.
# static/ext (the relabelled DuckDB-Wasm extensions) is git-ignored; build it as
# the README describes, or the browser can't load Quack.
FROM python:3.12-slim

# git: datarecord and mathspec install from GitHub.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /usr/local/bin/uv

WORKDIR /srv
ENV UV_PYTHON_DOWNLOADS=never UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# The server switches extension installs off once it serves, so install the
# ones it loads now.
RUN uv run --no-sync python -c "import duckdb; c = duckdb.connect(); [c.install_extension(e) for e in ('quack', 'httpfs', 'json')]"

# datarecord's S3 secret uses DuckDB's credential chain `env;config`, which
# refuses to validate without a `default` profile in ~/.aws/config, even when
# the key comes from the environment. An empty one is enough.
RUN mkdir -p /root/.aws && printf '[default]\n' > /root/.aws/config

COPY app ./app
COPY static ./static

ENV PORT=8080
CMD ["sh", "-c", "exec uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
