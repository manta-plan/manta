// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import "driver.js/dist/driver.css";
import App from "./App.tsx";

// Leftover of the removed default-project cache (`manta.defaultProjectUuid.<sub>`).
try {
  Object.keys(window.localStorage)
    .filter((key) => key.startsWith("manta.defaultProjectUuid."))
    .forEach((key) => window.localStorage.removeItem(key));
} catch {
  // Storage can be blocked; nothing to clean up then.
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
