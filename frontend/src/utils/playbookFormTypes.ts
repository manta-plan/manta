import type { FieldError } from "../features/playbook-config/validation";
import type { ResolvedSchema, SchemaGroup } from "./jsonSchema";
import type { BlockConfigSchema, Defs, JsonSchemaProperty } from "./playbookTypes";

export type JsonObject = Record<string, unknown>;

/** What every field needs to know about the step it belongs to. */
export type FormContext = {
  defs: Defs;
  idPrefix: string;
  /** The step's `inputs`: setting -> where another step supplies it. */
  inputs: Record<string, string>;
  /** The step's settings in the playbook's default config, to spot edits. */
  defaults: JsonObject;
  errors: FieldError[];
};

export type PlaybookConfigFormProps = {
  schema: BlockConfigSchema;
  value: JsonObject;
  onChange: (value: JsonObject) => void;
  /** Keeps element ids unique between steps. */
  idPrefix: string;
  inputs?: Record<string, string>;
  defaults?: JsonObject;
  errors?: FieldError[];
};

export type ObjectFieldsProps = {
  context: FormContext;
  path: string[];
  properties: Record<string, JsonSchemaProperty>;
  required: string[];
  value: JsonObject;
  onChange: (value: JsonObject) => void;
  /** Leave out nested groups: each is rendered as its own dropdown. */
  flat?: boolean;
};

export type ReadOnlyFieldProps = {
  id: string;
  name: string;
  property: JsonSchemaProperty;
  source: string | null;
};

export type FieldProps = {
  context: FormContext;
  id: string;
  name: string;
  path: string[];
  isRequired: boolean;
  resolved: ResolvedSchema;
  value: unknown;
  /** undefined removes the setting, so the block's own default applies. */
  onChange: (value: unknown) => void;
};

export type ArrayFieldProps = {
  id: string;
  item: ResolvedSchema;
  value: unknown[];
  onChange: (value: unknown) => void;
};

export type GroupSectionProps = {
  context: FormContext;
  group: SchemaGroup;
  groups: SchemaGroup[];
  root: JsonObject;
  onChange: (value: unknown) => void;
};

export type JsonFieldProps = {
  id: string;
  value: unknown;
  cleared: undefined;
  onChange: (value: unknown) => void;
};
