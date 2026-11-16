#   docker build -t manta-frontend frontend
FROM node:24-slim AS build
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY public public
COPY src src
RUN pnpm build

# Serves the static build and forwards /v1 to BACKEND_URL (see Caddyfile).
FROM caddy:2.11-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
ENV BACKEND_URL=http://backend:8000
EXPOSE 80
