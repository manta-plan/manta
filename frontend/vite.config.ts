import { execFileSync } from "node:child_process";
import { defineConfig, loadEnv } from "vite";
import react, { reactCompilerPreset } from "@vitejs/plugin-react";
import babel from "@rolldown/plugin-babel";
import tailwindcss from "@tailwindcss/vite";

function git(...args: string[]) {
  try {
    return execFileSync("git", args, { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "";
  }
}

// The git commit of the build and its date, shown in the About dialog and in
// feedback reports. A Docker build has no .git, so frontend/Dockerfile passes
// them in as GIT_COMMIT and GIT_COMMIT_DATE.
function appVersion() {
  const commit = process.env.GIT_COMMIT || git("rev-parse", "HEAD");
  return commit ? commit.slice(0, 7) : "unknown";
}

function appCommitDate() {
  return process.env.GIT_COMMIT_DATE || git("log", "-1", "--format=%cI") || "";
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // The record server's port and token are the compose stack's, in
  // backend/.env, so they're set once there.
  const quack = loadEnv(mode, "../backend", "QUACK_");
  const quackUrl = `http://127.0.0.1:${quack.QUACK_SERVER_PORT ?? 8010}`;
  process.env.VITE_RECORD_TOKEN ??= quack.QUACK_TOKEN;

  return {
    plugins: [tailwindcss(), react(), babel({ presets: [reactCompilerPreset()] })],
    define: {
      __APP_VERSION__: JSON.stringify(appVersion()),
      __APP_COMMIT_DATE__: JSON.stringify(appCommitDate()),
    },
    server: {
      proxy: {
        "/v1": "http://127.0.0.1:8000",
        // TEMPORARY: the record server (docker/quack-server), proxied like
        // frontend/Caddyfile does in a deploy, so the app reaches it on its
        // own origin in dev too: the catalogue API and the Quack relay.
        "/api": quackUrl,
        "/quack": quackUrl,
      },
    },
  };
});
