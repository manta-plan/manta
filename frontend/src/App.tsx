import { Button } from "@base-ui/react/button";
import type { FormEvent } from "react";
import { FiActivity, FiArrowRight, FiFeather, FiLock, FiUser } from "react-icons/fi";
import { Route, Switch, useLocation } from "wouter";

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

function HomePage() {
  return (
    <main className="bg-background text-text min-h-svh px-6 py-12 sm:py-16">
      <section className="mx-auto grid min-h-[calc(100svh-6rem)] w-full max-w-5xl items-center gap-10 md:grid-cols-[1.15fr_0.85fr]">
        <div>
          <div className="border-border bg-surface text-text-secondary mb-8 inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm font-medium">
            <span className="bg-accent size-2 rounded-full" aria-hidden="true" />
            Energy system modeling
          </div>

          <div className="text-primary-foreground shadow-primary/20 mb-6 flex size-16 items-center justify-center rounded-lg bg-[image:var(--gradient-logo)] shadow-lg">
            <FiFeather className="size-7" aria-hidden="true" />
          </div>

          <p className="text-secondary mb-3 text-sm font-semibold uppercase">
            Base UI + React Icons
          </p>
          <h1 className="max-w-2xl text-5xl font-semibold tracking-normal sm:text-6xl">
            Hello world
          </h1>
          <p className="text-text-secondary mt-5 max-w-xl text-base leading-7">
            MANTA brand tokens are now available through Tailwind utilities, with ocean blue, aurora
            teal, and energy lime mapped to reusable semantic colors.
          </p>

          <div className="mt-8 flex flex-wrap gap-3">
            <Button className="bg-primary text-primary-foreground shadow-primary/25 hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary inline-flex items-center gap-2 rounded-md px-4 py-2.5 text-sm font-semibold shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-2">
              Explore setup
              <FiArrowRight className="size-4" aria-hidden="true" />
            </Button>
            <Button className="border-border bg-surface text-primary hover:bg-surface-alt focus-visible:outline-secondary inline-flex items-center gap-2 rounded-md border px-4 py-2.5 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2">
              <FiActivity className="size-4" aria-hidden="true" />
              View tokens
            </Button>
          </div>
        </div>

        <aside className="border-border bg-surface shadow-primary/10 rounded-lg border p-5 shadow-xl">
          <div className="mb-5 h-32 rounded-md bg-[image:var(--gradient-hero)]" />
          <dl className="grid gap-3 text-sm">
            {[
              ["Primary", "bg-primary"],
              ["Secondary", "bg-secondary"],
              ["Accent", "bg-accent"],
            ].map(([label, utility]) => (
              <div
                className="bg-surface-alt flex items-center justify-between rounded-md px-3 py-2"
                key={label}
              >
                <dt className="text-text font-medium">{label}</dt>
                <dd className="text-text-secondary flex items-center gap-2">
                  <span className={`size-4 rounded-full ${utility}`} aria-hidden="true" />
                  {utility}
                </dd>
              </div>
            ))}
          </dl>
        </aside>
      </section>
    </main>
  );
}

function LoginPage() {
  const [, navigate] = useLocation();

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate("/");
  }

  return (
    <main className="bg-primary text-text relative flex min-h-svh items-center justify-center overflow-hidden px-6 py-10">
      <img
        src="/auth-background.jpg"
        alt=""
        className="absolute inset-0 size-full object-cover"
        aria-hidden="true"
      />
      <div
        className="absolute inset-0 bg-[linear-gradient(135deg,rgba(0,58,104,0.78),rgba(0,168,150,0.42),rgba(15,23,42,0.66))]"
        aria-hidden="true"
      />

      <section className="bg-surface/95 shadow-primary/35 relative w-full max-w-md rounded-lg border border-white/30 p-6 shadow-2xl backdrop-blur sm:p-8">
        <div className="mb-8">
          <img
            src="/auth-logo.png"
            alt="MANTA Energy"
            className="mx-auto mb-6 h-24 w-auto object-contain"
          />
          <p className="text-secondary mb-2 text-sm font-semibold uppercase">MANTA Energy</p>
          <h1 className="text-text text-3xl font-semibold tracking-normal">Enter your workspace</h1>
          <p className="text-text-secondary mt-3 text-sm leading-6">
            Model smarter energy systems with MANTA
          </p>
        </div>

        <form className="grid gap-5" onSubmit={handleSubmit}>
          <label className="text-text grid gap-2 text-sm font-medium" htmlFor="username">
            Username
            <span className="focus-within:border-secondary focus-within:ring-secondary/20 border-border bg-surface flex items-center gap-3 rounded-md border px-3 py-2.5 ring-0 transition focus-within:ring-4">
              <FiUser className="text-muted size-4" aria-hidden="true" />
              <input
                className="text-text placeholder:text-muted min-w-0 flex-1 bg-transparent text-base outline-none"
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                placeholder="Enter username"
              />
            </span>
          </label>

          <label className="text-text grid gap-2 text-sm font-medium" htmlFor="password">
            Password
            <span className="focus-within:border-secondary focus-within:ring-secondary/20 border-border bg-surface flex items-center gap-3 rounded-md border px-3 py-2.5 ring-0 transition focus-within:ring-4">
              <FiLock className="text-muted size-4" aria-hidden="true" />
              <input
                className="text-text placeholder:text-muted min-w-0 flex-1 bg-transparent text-base outline-none"
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="Enter password"
              />
            </span>
          </label>

          <div className="flex items-center text-sm">
            <label className="text-text-secondary flex items-center gap-2" htmlFor="remember">
              <input
                className="accent-secondary border-border size-4 rounded"
                id="remember"
                name="remember"
                type="checkbox"
              />
              Remember me
            </label>
          </div>

          <Button
            className="bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary shadow-primary/25 inline-flex items-center justify-center gap-2 rounded-md px-4 py-3 text-sm font-semibold shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-2"
            type="submit"
          >
            Sign in
            <FiArrowRight className="size-4" aria-hidden="true" />
          </Button>
        </form>
      </section>
    </main>
  );
}

export default App;
