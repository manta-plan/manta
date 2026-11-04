import type { Node } from "@xyflow/react";

// ── GET /v1/playbooks ───────────────────────────────────────────────────────

export type PlaybookStepSummary = {
  /** Step name within its playbook; the key its settings are filed under in a run's config. */
  name: string;
  /** Block the step runs. null for a step that runs a nested playbook. */
  block: string | null;
};

export type PlaybookSummary = {
  /** The playbook's own name; what POST /v1/runs takes as `playbook`. */
  name: string;
  steps: PlaybookStepSummary[];
};

export type ListPlaybooksResponse = {
  items: PlaybookSummary[];
  total: number;
};

// ── GET /v1/playbooks/{name} ────────────────────────────────────────────────

/** The subset of JSON Schema that Pydantic emits for a block's config. */
export type JsonSchemaType =
  | "string"
  | "integer"
  | "number"
  | "boolean"
  | "null"
  | "object"
  | "array";

export type JsonSchemaProperty = {
  type?: JsonSchemaType | JsonSchemaType[];
  /** e.g. `int | None` is [{ type: "integer" }, { type: "null" }]. */
  anyOf?: JsonSchemaProperty[];
  /** A reference into the block schema's `$defs`, e.g. "#/$defs/LinopyModelSchema". */
  $ref?: string;
  enum?: (string | number | boolean | null)[];
  const?: unknown;
  default?: unknown;
  /** Display name, e.g. "N Hours". The config key is the property's key, e.g. `n_hours`. */
  title?: string;
  description?: string;
  minimum?: number;
  maximum?: number;
  items?: JsonSchemaProperty;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  /** Set on settings another step fills in; not typed by a user. */
  "x-manta-input"?: unknown;
};

/** A block schema's `$defs`: def name -> its schema. */
export type Defs = Record<string, JsonSchemaProperty>;

export type BlockConfigSchema = {
  title?: string;
  type?: "object";
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  $defs?: Defs;
};

export type PlaybookStep = {
  name: string;
  block: string | null;
  block_summary: string | null;
  block_config_schema: BlockConfigSchema | null;
  when: { config: string; equals: unknown } | null;
  inputs: Record<string, string>;
};

/** Values filed by step name, plus a `globals` section. */
export type PlaybookConfig = Record<string, Record<string, unknown>>;

export type PlaybookDetail = {
  name: string;
  default_config: PlaybookConfig;
  steps: PlaybookStep[];
};

// ── POST /v1/playbooks/{name}/validate ──────────────────────────────────────

export type PlaybookIssue = {
  kind: string;
  message: string;
  step_path: string[];
  config_path: (string | number)[] | null;
  input: string | null;
};

export type ValidatePlaybookConfigResponse = {
  valid: boolean;
  issues: PlaybookIssue[];
};

// ── Dialog ──────────────────────────────────────────────────────────────────

export type PlaybookCanvasNode = Node<
  { label: string; block: string | null; inactive: boolean },
  "playbook"
>;

export type RunPlaybookDialogProps = {
  error: string | null;
  open: boolean;
  isSubmitting: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (name: string, playbook: string, config: PlaybookConfig) => Promise<void>;
};
