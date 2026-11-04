import { useEffect, useState } from "react";
import { getRecordCatalogue } from "./record-server";
import type { RecordCatalogue } from "./record-server";

let request: Promise<RecordCatalogue> | null = null;

// The record server's catalogue, fetched once per page load: the server lists
// its records at start and keeps them until it restarts.
export function useRecordCatalogue(): { catalogue: RecordCatalogue | null; error: string | null } {
  const [state, setState] = useState<{ catalogue: RecordCatalogue | null; error: string | null }>({
    catalogue: null,
    error: null,
  });
  useEffect(() => {
    let cancelled = false;
    if (!request) {
      request = getRecordCatalogue();
      // A failed request is forgotten, so the next use retries.
      request.catch(() => {
        request = null;
      });
    }
    request
      .then((catalogue) => !cancelled && setState({ catalogue, error: null }))
      .catch(
        (error: unknown) =>
          !cancelled &&
          setState({
            catalogue: null,
            error: error instanceof Error ? error.message : String(error),
          }),
      );
    return () => {
      cancelled = true;
    };
  }, []);
  return state;
}
