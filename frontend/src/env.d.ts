/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** The record server's shared dev token; it ships in the bundle. */
  readonly VITE_RECORD_TOKEN?: string;
}

/** Short git commit of the build, injected by vite.config.ts. */
declare const __APP_VERSION__: string;
