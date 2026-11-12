
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv

WORKDIR /app

COPY --from=playbook pyproject.toml README.md playbook/
COPY --from=playbook-library pyproject.toml README.md playbook-library/
COPY --from=runner pyproject.toml README.md runner/
COPY pyproject.toml uv.lock README.md backend/

WORKDIR /app/backend

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace

WORKDIR /app

COPY --from=playbook src playbook/src
COPY --from=playbook-library src playbook-library/src
COPY --from=runner src runner/src
COPY src backend/src

WORKDIR /app/backend

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENV APP_HOST=0.0.0.0

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "manta"]
