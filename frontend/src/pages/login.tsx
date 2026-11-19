import type { SubmitEvent } from "react";
import { useState } from "react";
import { FiAlertCircle, FiRefreshCw } from "react-icons/fi";
import { ApiError } from "../api/manta";
import { login } from "../features/auth/api";
import { AuthButton } from "../features/auth/components/auth-button";
import { AuthTextField } from "../features/auth/components/auth-text-field";
import { MantaLogo } from "../features/auth/components/manta-logo";

// The photo's average color, so the page never flashes from the app
// background to the photo once it loads on a slow network.
const authBackgroundColor = "#42645e";

export function LoginPage() {
  const [isBackgroundLoaded, setIsBackgroundLoaded] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [signInError, setSignInError] = useState<string | null>(null);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);

    setIsSigningIn(true);
    setSignInError(null);

    try {
      // A successful login updates the session, and the router then moves on
      // to the home page.
      await login({
        username: String(formData.get("username") ?? "").trim(),
        password: String(formData.get("password") ?? ""),
        remember: formData.get("remember") === "on",
      });
    } catch (error) {
      setSignInError(getSignInErrorMessage(error));
      setIsSigningIn(false);
    }
  }

  return (
    <main
      className="relative flex min-h-svh w-full items-center justify-center overflow-hidden px-6 py-10"
      style={{ backgroundColor: authBackgroundColor }}
    >
      <img
        src="/auth-background.jpg"
        alt=""
        aria-hidden="true"
        fetchPriority="high"
        onLoad={() => setIsBackgroundLoaded(true)}
        className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${
          isBackgroundLoaded ? "opacity-100" : "opacity-0"
        }`}
      />
      <div className="absolute inset-0 bg-slate-900/25" aria-hidden="true" />

      {/* A fixed light card: the wordmark's dark text needs a guaranteed light backdrop. */}
      <section className="auth-card-enter relative w-full max-w-sm rounded-lg bg-white/95 p-6 shadow-2xl backdrop-blur-sm">
        <div className="auth-logo-enter mb-6 flex justify-center">
          <MantaLogo markHeight={28} />
        </div>

        <h1 className="mb-4 text-center text-[13px] font-medium text-slate-500">
          Log in to your account
        </h1>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <AuthTextField
            label="Username"
            name="username"
            type="text"
            autoComplete="username"
            placeholder="Enter username"
          />
          <AuthTextField
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            placeholder="••••••••"
          />

          <label className="flex items-center gap-2 text-[12px] text-slate-500">
            <input className="accent-secondary size-3.5 rounded" name="remember" type="checkbox" />
            Remember me
          </label>

          {signInError !== null ? (
            <p
              className="flex items-start gap-2 rounded border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-700"
              role="alert"
            >
              <FiAlertCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              {signInError}
            </p>
          ) : null}

          <AuthButton
            type="submit"
            variant="primary"
            disabled={isSigningIn}
            className="mt-2"
            icon={
              isSigningIn ? (
                <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
              ) : undefined
            }
          >
            {isSigningIn ? "Signing in..." : "Log In"}
          </AuthButton>
        </form>
      </section>
    </main>
  );
}

function getSignInErrorMessage(error: unknown) {
  if (error instanceof ApiError && error.status === 401) {
    return "Invalid username or password.";
  }

  return "Unable to sign in right now. Please try again.";
}
