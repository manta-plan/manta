import { useEffect } from "react";
import { Redirect, Route, Switch } from "wouter";
import { useSessionUser } from "./features/auth/session";
import { HOME_ROUTES } from "./features/home/routes";
import { useAppStore } from "./features/home/store";
import { HomePage } from "./pages/home";
import { LoginPage } from "./pages/login";
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
    <Switch>
      <Route path="/login">
        <Redirect to="/" replace />
      </Route>
      <Route path="/project/:projectId">
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
  );
}

export default App;
