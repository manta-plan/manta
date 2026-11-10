#   docker build -t manta-frontend frontend
FROM node:24-slim
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY index.html vite.config.ts tsconfig.json tsconfig.app.json tsconfig.node.json ./
COPY public public
COPY src src

# Vite's dev server proxies /v1 to BACKEND_URL (see vite.config.ts).
ENV BACKEND_URL=http://backend:8000
EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
