import { Redirect, Route, Switch } from "wouter";
import { useSessionUser } from "./features/auth/session";
import { HomePage } from "./pages/home";
import { LoginPage } from "./pages/login";

function App() {
  const isSignedIn = useSessionUser() !== null;

  return (
    <Switch>
      <Route path="/login">{isSignedIn ? <Redirect to="/" replace /> : <LoginPage />}</Route>
      <Route>{isSignedIn ? <HomePage /> : <Redirect to="/login" replace />}</Route>
    </Switch>
  );
}

export default App;
