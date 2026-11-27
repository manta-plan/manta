#   docker build -t manta-frontend frontend
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
# "false" hides the "Continue as guest" button (the backend's GUEST_LOGIN_ENABLED).
ARG VITE_GUEST_LOGIN_ENABLED
RUN pnpm build

# Serves the static build, forwards /v1 to BACKEND_URL and the record server's
# paths to QUACK_URL (see Caddyfile).
FROM caddy:2.11-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
ENV BACKEND_URL=http://backend:8000
ENV QUACK_URL=http://quack-server:8080
EXPOSE 80
