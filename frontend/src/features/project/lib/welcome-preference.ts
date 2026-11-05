// Global "Don't show this again" for the project welcome dialog — per
// browser, like the theme preference. The per-project "already seen" flag
// lives on the Project record instead (Project.showWelcome).
const WELCOME_DISABLED_STORAGE_KEY = "manta-welcome-dialog-disabled";

export function isWelcomeDialogDisabled(): boolean {
  try {
    return localStorage.getItem(WELCOME_DISABLED_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

export function setWelcomeDialogDisabled(disabled: boolean) {
  try {
    if (disabled) localStorage.setItem(WELCOME_DISABLED_STORAGE_KEY, "true");
    else localStorage.removeItem(WELCOME_DISABLED_STORAGE_KEY);
  } catch {
    // Storage unavailable (private mode etc.) — the dialog just shows again.
  }
}
