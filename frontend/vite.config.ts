import { execFileSync } from "node:child_process";
import { defineConfig } from "vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";
import tailwindcss from "@tailwindcss/vite";

// The short git commit of the build, shown in feedback reports.
function appVersion() {
  try {
    return execFileSync("git", ["rev-parse", "--short", "HEAD"], {
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return "unknown";
  }
}

// The record server's host port (QUACK_SERVER_PORT in backend/.env).
const quackUrl = process.env.QUACK_URL ?? "http://127.0.0.1:8010";

// https://vite.dev/config/
export default defineConfig({
  plugins: [tailwindcss(), react(), babel({ presets: [reactCompilerPreset()] })],
  define: {
    __APP_VERSION__: JSON.stringify(appVersion()),
  },
  server: {
    proxy: {
      "/v1": "http://127.0.0.1:8000",
      // TEMPORARY: the record server (docker/quack-server), proxied like
      // frontend/Caddyfile does in a deploy, so the app reaches it on its own
      // origin in dev too: the catalogue API, the Quack relay and the
      // DuckDB-Wasm extensions. QUACK_URL overrides where it listens.
      "/api": quackUrl,
      "/quack": quackUrl,
      "/ext": quackUrl,
    },
  },
});
