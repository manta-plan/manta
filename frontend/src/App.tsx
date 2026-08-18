import { Route, Switch } from "wouter";
import { HomePage } from "./pages/home";
import { LoginPage } from "./pages/login";

function App() {
  return (
    <Switch>
      <Route path="/login">
        <LoginPage />
      </Route>
      <Route>
        <HomePage />
      </Route>
    </Switch>
  );
}

export default App;
