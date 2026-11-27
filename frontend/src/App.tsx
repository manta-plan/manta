// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Tooltip } from "@base-ui/react/tooltip";
import { useEffect } from "react";
import { Redirect, Route, Switch } from "wouter";
import { SWRConfig } from "swr";
import { AppToasts } from "./components/app-toasts";
import { useSessionUser } from "./features/auth/session";
import { HOME_ROUTES } from "./features/home/routes";
import { useAppStore } from "./features/home/store";
import { HomePage } from "./pages/home";
import { LoginPage } from "./pages/login";
import { recordSWRConfig } from "./features/project/lib/record-data";
import { ProjectPage } from "./pages/project";

function App() {
  const isSignedIn = useSessionUser() !== null;
  const theme = useAppStore((state) => state.theme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  if (!isSignedIn) {
    return (
      <Switch>
        <Route path="/login">
          <LoginPage />
        </Route>
        <Route>
          <Redirect to="/login" replace />
        </Route>
      </Switch>
    );
  }

  return (
    // One cache of record reads for every tab (record-data.ts).
    <SWRConfig value={recordSWRConfig}>
      <Tooltip.Provider delay={400} closeDelay={0}>
        <AppToasts>
          <Switch>
            <Route path="/login">
              <Redirect to="/" replace />
            </Route>
            <Route path="/project/:projectId/:tab?/:detailId?">
              <ProjectPage />
            </Route>
            {HOME_ROUTES.map((route) => (
              <Route key={route.id} path={route.path}>
                <HomePage />
              </Route>
            ))}
            <Route>
              <Redirect to="/" replace />
            </Route>
          </Switch>
        </AppToasts>
      </Tooltip.Provider>
    </SWRConfig>
  );
}

export default App;
