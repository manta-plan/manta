// Manta feedback → Google Sheet and Drive.
//
// The backend (POST /v1/feedback) forwards each feedback here. This script only
// appends: it checks the shared secret, adds a row and saves the screenshot. It
// has no way to read, list, change or delete stored feedback, so feedback
// survives a compromised or wiped app.
//
// Sheet columns (row 1 = headers):
//   A Timestamp | B Category | C Message | D Page | E Screenshot ID | F User agent |
//   G Window size | H App version | I Username | J Status | K Notes
// J and K are for triage and are never written here (Status is seeded with "New").
//
// Script properties (Project settings → Script properties), never in the source:
//   SECRET     the shared secret; the same value as the backend's FEEDBACK_SCRIPT_SECRET
//   FOLDER_ID  the Drive folder the screenshots go to
//
// The backend POSTs JSON as text/plain, read from e.postData.contents.
// Deploy as a web app that runs as you, with access for anyone, and put its
// /exec address in the backend's FEEDBACK_SCRIPT_URL. The secret is the only gate.

const SHEET_NAME = "Feedback"; // falls back to the first sheet if missing
const CATEGORIES = ["bug_report", "feature_request", "pain_point", "question"];
const MAX_IMAGE_BYTES = 6 * 1024 * 1024;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

function doPost(e) {
  try {
    const props = PropertiesService.getScriptProperties();
    const data = JSON.parse((e && e.postData && e.postData.contents) || "{}");

    if (!safeEqual(String(data.secret || ""), props.getProperty("SECRET") || "")) {
      return json({ ok: false, error: "Forbidden" });
    }
    const message = clip(data.message, 2000);
    if (!message) return json({ ok: false, error: "Empty message" });

    // Save the screenshot before taking the lock: the Drive upload is the slow
    // part, and only the row append needs serialising.
    const screenshotId = String(data.screenshot_id || "");
    if (data.screenshot) {
      if (!UUID_PATTERN.test(screenshotId)) return json({ ok: false, error: "Invalid screenshot ID" });
      const bytes = Utilities.base64Decode(String(data.screenshot));
      if (bytes.length > MAX_IMAGE_BYTES) return json({ ok: false, error: "Image too large" });
      DriveApp.getFolderById(props.getProperty("FOLDER_ID"))
        .createFile(Utilities.newBlob(bytes, "image/png", screenshotId + ".png"));
    }

    const lock = LockService.getScriptLock();
    if (!lock.tryLock(10000)) return json({ ok: false, error: "busy" });
    try {
      const ss = SpreadsheetApp.getActiveSpreadsheet();
      const sheet = ss.getSheetByName(SHEET_NAME) || ss.getSheets()[0];
      sheet.appendRow([
        new Date(),                                      // A Timestamp
        oneOf(data.category, CATEGORIES, "question"),    // B Category
        message,                                         // C Message
        clip(data.page, 300),                            // D Page
        data.screenshot ? screenshotId : "",             // E Screenshot ID
        clip(data.user_agent, 300),                      // F User agent
        clip(data.window_size, 20),                      // G Window size
        clip(data.app_version, 50),                      // H App version
        clip(data.username, 200),                        // I Username
        "New",                                           // J Status
        "",                                              // K Notes
      ]);
    } finally {
      lock.releaseLock();
    }
    return json({ ok: true });
  } catch (err) {
    return json({ ok: false, error: err.message });
  }
}

// Leading =, +, - or @ would make Sheets evaluate user text as a formula.
function clip(value, max) {
  const text = String(value == null ? "" : value).trim().slice(0, max);
  return /^[=+\-@]/.test(text) ? "'" + text : text;
}

function oneOf(value, allowed, fallback) {
  return allowed.indexOf(value) !== -1 ? value : fallback;
}

// Compares without stopping at the first difference.
function safeEqual(a, b) {
  if (!b || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
