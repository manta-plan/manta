import { Route, Switch } from "wouter";
import { HomePage } from "./pages/home";
import { LoginPage } from "./pages/login";
import { ResultPage } from "./pages/result";

function App() {
  return (
    <Switch>
      <Route path="/login">
        <LoginPage />
      </Route>
      <Route path="/result/:slug">{(params) => <ResultPage slug={params.slug} />}</Route>
      <Route>
        <HomePage />
      </Route>
    </Switch>
  );
}

export default App;
