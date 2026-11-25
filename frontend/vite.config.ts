// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { execFileSync } from "node:child_process";
import { defineConfig, loadEnv } from "vite";
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
