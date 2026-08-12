# This sample image mainly demonstrates how the frontend build step is handled
# for static frontend serving.

# --- Build stage ---
FROM node:26-alpine AS build
WORKDIR /app

RUN npm install -g pnpm@11.10.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
RUN pnpm build

# --- Serve stage ---
FROM caddy:2-alpine

COPY --from=build /app/dist /usr/share/caddy

RUN cat <<EOF > /etc/caddy/Caddyfile
:80 {
    root * /usr/share/caddy
    try_files {path} /index.html
    file_server
    encode gzip zstd

    @assets {
        path /assets/*
    }
    header @assets Cache-Control "public, max-age=31536000, immutable"
}
EOF

EXPOSE 80
