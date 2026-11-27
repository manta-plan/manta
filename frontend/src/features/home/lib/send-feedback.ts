import { postJson } from "../../../api/manta";

export type FeedbackCategory = "bug_report" | "feature_request" | "pain_point" | "question";

export interface FeedbackInput {
  category: FeedbackCategory;
  message: string;
  /** Empty when the user opts out of sharing the current page. */
  page: string;
  /** Base64 PNG of the Manta page, when the user keeps it. */
  screenshot?: string;
}

/**
 * Posts feedback to the backend, which adds the username and forwards it to the
 * team's Google Sheet. Only signed-in users can send it.
 */
export async function sendFeedback(input: FeedbackInput): Promise<void> {
  await postJson("/v1/feedback", {
    category: input.category,
    message: input.message,
    page: input.page || null,
    screenshot: input.screenshot ?? null,
    user_agent: navigator.userAgent,
    window_size: `${window.innerWidth}×${window.innerHeight}`,
    app_version: __APP_VERSION__,
  });
}
