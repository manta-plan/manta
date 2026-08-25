import { Button } from "@base-ui/react/button";
import type { SubmitEvent } from "react";
import { useState } from "react";
import { FiArrowRight, FiLock, FiUser } from "react-icons/fi";
import { useLocation } from "wouter";

export function LoginPage() {
  const [isBackgroundLoaded, setIsBackgroundLoaded] = useState(false);
  const [, navigate] = useLocation();

  function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    navigate("/");
  }

  return (
    <main
      className="bg-primary text-text relative flex min-h-svh items-center justify-center overflow-hidden bg-cover bg-center px-6 py-10"
      style={{ backgroundImage: "url('/auth-background-placeholder.jpg')" }}
    >
      <img
        src="/auth-background.jpg"
        alt=""
        className={`absolute inset-0 size-full object-cover transition-[filter,opacity,transform] duration-700 ease-out ${
          isBackgroundLoaded ? "blur-0 scale-100 opacity-100" : "scale-105 opacity-0 blur-md"
        }`}
        aria-hidden="true"
        onLoad={() => setIsBackgroundLoaded(true)}
      />
      <div
        className="absolute inset-0 bg-[linear-gradient(135deg,rgba(0,58,104,0.78),rgba(0,168,150,0.42),rgba(15,23,42,0.66))]"
        aria-hidden="true"
      />

      <section className="bg-surface/95 shadow-primary/35 relative w-full max-w-md rounded-lg border border-white/30 p-6 shadow-2xl backdrop-blur motion-safe:animate-[auth-card-enter_480ms_ease-out] sm:p-8">
        <div className="mb-8">
          <img
            src="/auth-logo.png"
            alt="MANTA Energy"
            className="mx-auto mb-6 h-24 w-auto object-contain"
          />
          <h1 className="text-text text-center text-3xl font-semibold tracking-normal">
            Sign in to your account
          </h1>
          <p className="text-text-secondary mt-3 text-center text-sm leading-6">
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
