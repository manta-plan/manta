import type { Theme } from "../store";

const FEEDBACK_ENDPOINT = import.meta.env.VITE_FEEDBACK_ENDPOINT;

export type FeedbackKind = "bug" | "idea" | "other";

export interface FeedbackInput {
  type: FeedbackKind;
  message: string;
  /** Empty when the user opts out of sharing the current page. */
  page: string;
  theme: Theme;
  /** Honeypot: a hidden form field only bots fill in; the sheet drops those rows. */
  website: string;
  /** Optional screenshot; the sheet saves it to Drive and links it in the Image column. */
  image?: { name: string; type: string; base64: string };
}

/**
 * Posts one feedback row to the Apps Script web app (see the sheet's
 * doPost). The body is JSON sent as text/plain: a "simple" request, so the
 * browser skips the CORS preflight Apps Script can't answer. Without an
 * endpoint configured it resolves without sending, keeping the form usable
 * in local setups.
 */
export async function sendFeedback(input: FeedbackInput): Promise<void> {
  if (!FEEDBACK_ENDPOINT) return;

  const response = await fetch(FEEDBACK_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "text/plain;charset=utf-8" },
    body: JSON.stringify({
      ...input,
      // Login is decorative for now, so there's no real user to report;
      // the sheet keeps the column for when auth lands.
      user: "",
      appVersion: __APP_VERSION__,
      browser: navigator.userAgent,
      screen: `${window.innerWidth}×${window.innerHeight}`,
    }),
  });
  const result = (await response.json()) as { ok: boolean; error?: string };
  if (!result.ok) throw new Error(result.error ?? "Feedback was rejected");
}
