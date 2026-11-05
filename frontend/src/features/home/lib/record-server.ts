// The record server serves datarecord stores that an admin uploads to its
// bucket. Only its catalogue is read here: the list of records a project can
// be created from.

// A record in the catalogue, as listed without opening it.
export type RecordSummary = {
  id: string;
  label: string;
  description: string;
  // Its named revisions, scenarios and run results alike.
  revisions: string[];
  size: number;
  modified: string | null;
  files: number;
  // Open on the server now: records open when a project first uses them.
  open: boolean;
  // Why it last failed to open; it is retried on the next use.
  error: string | null;
};

export type RecordCatalogue = {
  records: RecordSummary[];
  // What a project that names no record opens.
  default: string | null;
};

export type RecordServerConfig = {
  // host:port of the record server.
  server: string;
  // Shared dev token: it ships in the static bundle, so it is not a secret.
  token: string;
};

export function recordServerConfig(): RecordServerConfig {
  const server = import.meta.env.VITE_RECORD_SERVER;

  // The Manta backend does not serve a record catalogue, so there is no
  // sensible default: the catalogue stays unreachable until this is set.
  if (!server) {
    throw new Error("VITE_RECORD_SERVER is not set.");
  }

  return { server, token: import.meta.env.VITE_RECORD_TOKEN ?? "" };
}

export function isSecure(server: string) {
  const host = server.split(":")[0];
  return window.location.protocol === "https:" || !["localhost", "127.0.0.1"].includes(host);
}

export async function getRecordCatalogue(): Promise<RecordCatalogue> {
  const config = recordServerConfig();
  const protocol = isSecure(config.server) ? "https" : "http";
  const response = await fetch(`${protocol}://${config.server}/api/records`, {
    headers: { Authorization: `Bearer ${config.token}` },
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("The record server refused the token.");
    }

    throw new Error(`GET /api/records: HTTP ${response.status}`);
  }

  return (await response.json()) as RecordCatalogue;
}
