/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Google Apps Script web-app URL that appends feedback rows to a sheet. */
  readonly VITE_FEEDBACK_ENDPOINT?: string;
  /** host:port of the record server that lists the data catalog. */
  readonly VITE_RECORD_SERVER?: string;
  /** The record server's shared dev token; it ships in the bundle. */
  readonly VITE_RECORD_TOKEN?: string;
}

/** Short git commit of the build, injected by vite.config.ts. */
declare const __APP_VERSION__: string;
