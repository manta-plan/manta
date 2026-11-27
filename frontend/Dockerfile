#   docker build -t manta-frontend frontend
#
# Add `--build-context git=.git` to show the commit in the About dialog;
# docker/compose-dev-fullstack.yaml does.

# The repo's .git when passed as the `git` build context, which replaces this
# empty stage. Without it the About dialog shows the commit as "unknown".
FROM scratch AS git

# Reads the commit and its date. Its output only changes with the commit, so
# other changes to .git (fetches, the index) leave the app build cached.
FROM alpine:3.22 AS version
RUN apk add --no-cache git
RUN --mount=type=bind,from=git,target=/repo.git \
  mkdir /version \
  && git -c safe.directory='*' --git-dir=/repo.git rev-parse HEAD >/version/commit 2>/dev/null \
  ; git -c safe.directory='*' --git-dir=/repo.git log -1 --format=%cI >/version/date 2>/dev/null \
  ; true

FROM node:24-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY public public
COPY src src
# Vite inlines VITE_* variables at build time, so the record server's shared dev
# token is a build arg, not runtime env. The app reaches the record server on
# this site's own origin, which proxies it (see Caddyfile).
ARG VITE_RECORD_TOKEN
# The commit and date shown in the About dialog (see vite.config.ts).
COPY --from=version /version /version
RUN GIT_COMMIT=$(cat /version/commit) GIT_COMMIT_DATE=$(cat /version/date) pnpm build

# Serves the static build, forwards /v1 to BACKEND_URL and the record server's
# paths to QUACK_URL (see Caddyfile).
FROM caddy:2.11-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
ENV BACKEND_URL=http://backend:8000
ENV QUACK_URL=http://quack-server:8080
EXPOSE 80
