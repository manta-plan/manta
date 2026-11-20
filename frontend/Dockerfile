#   docker build -t manta-frontend frontend
FROM node:24-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY public public
COPY src src
# Vite inlines VITE_* variables at build time, so the record server's address
# (host[:port]; unset means this site's own origin, which proxies it, see
# Caddyfile) and its shared dev token are build args, not runtime env.
ARG VITE_RECORD_SERVER
ARG VITE_RECORD_TOKEN
RUN pnpm build

# Serves the static build, forwards /v1 to BACKEND_URL and the record server's
# paths to QUACK_URL (see Caddyfile).
FROM caddy:2.11-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
ENV BACKEND_URL=http://backend:8000
ENV QUACK_URL=http://quack-server:8080
EXPOSE 80
