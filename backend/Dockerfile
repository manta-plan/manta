FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv

WORKDIR /app
COPY --from=playbook pyproject.toml README.md playbook/
COPY --from=playbook src playbook/src
COPY --from=playbook-library pyproject.toml README.md playbook-library/
COPY --from=playbook-library src playbook-library/src
COPY --from=runner pyproject.toml README.md runner/
COPY --from=runner src runner/src
COPY pyproject.toml uv.lock README.md backend/
COPY src backend/src

WORKDIR /app/backend
RUN uv sync --locked --no-dev

ENV APP_HOST=0.0.0.0
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "manta"]
