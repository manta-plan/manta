import { useState } from "react";
import { getIn } from "../../playbook-config/conditions";
import { blockedSettings } from "../../playbook-config/exclusiveSettings";
import { isObject, setIn, withKey } from "../../../utils/jsonObject";
import {
  collectGroups,
  groupLabel,
  humanize,
  isConstant,
  isLinkedInput,
  resolveSchema,
  seedDefaults,
} from "../../../utils/jsonSchema";
import type {
  ArrayFieldProps,
  FieldProps,
  FormContext,
  GroupSectionProps,
  JsonFieldProps,
  ObjectFieldsProps,
  PlaybookConfigFormProps,
  ReadOnlyFieldProps,
} from "../../../utils/playbookFormTypes";

const inputClassName =
  "border-border bg-surface text-text focus:border-primary focus:ring-primary/20 h-10 w-full rounded-md border px-3 text-sm transition outline-none focus:ring-2";

/**
 * Renders a form for one step's settings, from its block's JSON schema: what you
 * can edit, and with which kind of input, follows the properties the block declares.
 * A setting has three states: unset (the block's default applies), null (only where
 * the schema allows it) and a value; the reset button returns a setting to unset.
 */
export function PlaybookConfigForm({
  schema,
  value,
  onChange,
  idPrefix,
  inputs = {},
  defaults = {},
  errors = [],
  exclusive = [],
}: PlaybookConfigFormProps) {
  const context: FormContext = {
    defs: schema.$defs ?? {},
    idPrefix,
    inputs,
    defaults,
    errors,
    exclusive,
  };
  const groups = collectGroups(schema.properties ?? {}, context.defs);
  const properties = schema.properties ?? {};

  if (Object.keys(properties).length === 0) {
    return <p className="text-text-secondary text-xs">This block has no settings to configure.</p>;
  }

  return (
    <div className="grid gap-4">
      <ObjectFields
        context={context}
        flat
        onChange={onChange}
        path={[]}
        properties={properties}
        required={schema.required ?? []}
        value={value}
      />
      {groups.map((group) => (
        <GroupSection
          context={context}
          group={group}
          groups={groups}
          key={group.path.join(".")}
          onChange={(next) => onChange(setIn(value, group.path, next))}
          root={value}
        />
      ))}
    </div>
  );
}

function ObjectFields({
  context,
  path,
  properties,
  required,
  value,
  onChange,
  flat = false,
}: ObjectFieldsProps) {
  const entries = Object.entries(properties).filter(
    ([key, property]) =>
      !flat ||
      isConstant(property) ||
      !(isLinkedInput(property)
        ? resolveSchema(key, property, context.defs).defName !== null
        : resolveSchema(key, property, context.defs).kind === "object"),
  );

  if (entries.length === 0) {
    return flat ? null : (
      <p className="text-text-secondary text-xs">This block has no settings to configure.</p>
    );
  }

  // Only the step's own top-level settings can exclude each other.
  const blocked = path.length === 0 ? blockedSettings(context.exclusive, value) : new Set<string>();

  return (
    <div className="grid gap-4">
      {entries.map(([key, property]) => {
        const fieldPath = [...path, key];
        const id = `${context.idPrefix}.${fieldPath.join(".")}`;

        if (isLinkedInput(property) || isConstant(property)) {
          return (
            <ReadOnlyField
              id={id}
              key={key}
              name={key}
              property={property}
              source={path.length === 0 ? (context.inputs[key] ?? null) : null}
            />
          );
        }

        return (
          <Field
            context={context}
            id={id}
            isBlocked={blocked.has(key)}
            isRequired={required.includes(key)}
            key={key}
            name={key}
            onChange={(next) => onChange(withKey(value, key, next))}
            path={fieldPath}
            resolved={resolveSchema(key, property, context.defs)}
            value={value[key]}
          />
        );
      })}
    </div>
  );
}

// A fixed value, or one another step fills in: shown so the setting is visible, but
// never editable and never part of the config that is sent.
function ReadOnlyField({ id, name, property, source }: ReadOnlyFieldProps) {
  const label = property.title ?? name;
  const linked = isLinkedInput(property);
  const stepName = source === null ? null : /^\$\{steps\.([^.}]+)\./.exec(source)?.[1];

  return (
    <div className="grid gap-1">
      <span className="text-sm font-semibold" id={id}>
        {label}
      </span>
      <span
        aria-labelledby={id}
        className="border-border bg-surface-alt text-text-secondary inline-flex h-10 items-center rounded-md border px-3 text-sm"
      >
        {linked
          ? stepName
            ? `Linked from step ${stepName}`
            : "Linked from another step"
          : String(property.const)}
      </span>
    </div>
  );
}

function Field({
  context,
  id,
  name,
  path,
  isRequired,
  isBlocked = false,
  resolved,
  value,
  onChange,
}: FieldProps) {
  const { kind, schema, nullable, label, description } = resolved;
  const placeholder =
    resolved.hasDefault && resolved.defaultValue !== null ? String(resolved.defaultValue) : "";
  // Clearing an input means "use the default", never null; null is the toggle's job.
  const cleared = undefined;
  const isNull = value === null;
  const isModified = JSON.stringify(value) !== JSON.stringify(getIn(context.defaults, path));
  const error = context.errors.find((item) => item.path === path.join("/"))?.message ?? null;

  const heading = (
    <div className="flex items-center justify-between gap-2">
      <label className="text-sm font-semibold" htmlFor={id}>
        {label}
        <span className="text-text-secondary ml-2 text-xs font-normal">
          {nullable ? " optional" : isRequired && !resolved.hasDefault ? "required" : ""}
        </span>
        {isModified ? (
          <span className="text-primary ml-2 text-xs font-normal">modified</span>
        ) : null}
      </label>
      <div className="flex items-center gap-3">
        {nullable ? (
          <label
            className="text-text-secondary flex items-center gap-1 text-xs"
            htmlFor={`${id}.null`}
          >
            <input
              checked={isNull}
              className="accent-primary size-3.5"
              id={`${id}.null`}
              onChange={(event) => onChange(event.target.checked ? null : cleared)}
              type="checkbox"
            />
            null
          </label>
        ) : null}
        {value !== undefined ? (
          <button
            className="text-text-secondary hover:text-text text-xs underline"
            onClick={() => onChange(undefined)}
            type="button"
          >
            Reset
          </button>
        ) : null}
      </div>
    </div>
  );
  const footer = (
    <>
      {description === null ? null : <p className="text-text-secondary text-xs">{description}</p>}
      {isBlocked ? (
        <p className="text-text-secondary text-xs">
          Unavailable while the other option is set. Reset it first.
        </p>
      ) : null}
      {error === null ? null : <p className="text-xs text-red-700">{error}</p>}
    </>
  );

  if (kind === "boolean") {
    return (
      <div className="grid gap-1">
        {heading}
        <input
          aria-label={label}
          checked={typeof value === "boolean" ? value : resolved.defaultValue === true}
          className="accent-primary size-4"
          disabled={isNull || isBlocked}
          id={id}
          onChange={(event) => onChange(event.target.checked)}
          type="checkbox"
        />
        {footer}
      </div>
    );
  }

  if (kind === "enum") {
    return (
      <div className="grid gap-2">
        {heading}
        <select
          className={inputClassName}
          disabled={isNull || isBlocked}
          id={id}
          onChange={(event) => onChange(event.target.value === "" ? cleared : event.target.value)}
          value={typeof value === "string" ? value : ""}
        >
          <option value="">{placeholder === "" ? "—" : `Default (${placeholder})`}</option>
          {(schema.enum ?? []).map((option) => (
            <option key={String(option)} value={String(option)}>
              {String(option)}
            </option>
          ))}
        </select>
        {footer}
      </div>
    );
  }

  if (kind === "integer" || kind === "number") {
    return (
      <div className="grid gap-2">
        {heading}
        <input
          className={inputClassName}
          disabled={isNull || isBlocked}
          id={id}
          max={schema.maximum}
          min={schema.minimum}
          onChange={(event) =>
            onChange(event.target.value === "" ? cleared : Number(event.target.value))
          }
          placeholder={placeholder}
          step={kind === "integer" ? 1 : "any"}
          type="number"
          value={typeof value === "number" ? value : ""}
        />
        {footer}
      </div>
    );
  }

  if (kind === "string") {
    return (
      <div className="grid gap-2">
        {heading}
        <input
          className={inputClassName}
          disabled={isNull || isBlocked}
          id={id}
          onChange={(event) => onChange(event.target.value === "" ? cleared : event.target.value)}
          placeholder={placeholder}
          type="text"
          value={typeof value === "string" ? value : ""}
        />
        {footer}
      </div>
    );
  }

  if (kind === "array") {
    return (
      <div className="grid gap-2">
        {heading}
        {isNull ? null : (
          <ArrayField
            id={id}
            item={resolveSchema(name, schema.items ?? {}, context.defs)}
            onChange={onChange}
            value={
              Array.isArray(value)
                ? value
                : ((resolved.defaultValue as unknown[] | undefined) ?? [])
            }
          />
        )}
        {footer}
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      {heading}
      {isNull ? null : <JsonField cleared={cleared} id={id} onChange={onChange} value={value} />}
      {footer}
    </div>
  );
}

// A list of plain values: one input per item, with add and remove.
function ArrayField({ id, item, value, onChange }: ArrayFieldProps) {
  const isNumber = item.kind === "integer" || item.kind === "number";
  const empty = item.kind === "boolean" ? false : isNumber ? 0 : "";

  return (
    <div className="grid gap-2">
      {value.map((entry, index) => (
        <div className="flex items-center gap-2" key={index}>
          <input
            aria-label={`${item.label} ${index + 1}`}
            className={inputClassName}
            id={index === 0 ? id : undefined}
            onChange={(event) => {
              const raw = event.target.value;
              const next = isNumber ? Number(raw) : raw;
              onChange(value.map((current, i) => (i === index ? next : current)));
            }}
            step={item.kind === "integer" ? 1 : "any"}
            type={isNumber ? "number" : "text"}
            value={String(entry ?? "")}
          />
          <button
            aria-label={`Remove ${item.label} ${index + 1}`}
            className="text-text-secondary hover:text-text text-sm"
            onClick={() => onChange(value.filter((_, i) => i !== index))}
            type="button"
          >
            Remove
          </button>
        </div>
      ))}
      <button
        className="text-primary w-fit text-sm font-semibold"
        onClick={() => onChange([...value, empty])}
        type="button"
      >
        Add {item.label}
      </button>
    </div>
  );
}

// One dropdown per schema def. A nullable group has an on/off switch: off sends null,
// on seeds the group from its own defaults. Its own nested groups are separate siblings.
function GroupSection({ context, group, groups, root, onChange }: GroupSectionProps) {
  const { resolved, path, properties, required, linked } = group;
  const id = `${context.idPrefix}.${path.join(".")}`;
  const label = groupLabel(resolved);
  const value = getIn(root, path);
  const isEnabled = isObject(value);
  const { nullable } = resolved;
  const parent = groups.find(
    (other) =>
      other.path.length === path.length - 1 && other.path.every((key, i) => key === path[i]),
  );
  const parentValue = parent === undefined ? undefined : getIn(root, parent.path);
  const blocked =
    parent !== undefined &&
    (parentValue === null || (parent.resolved.nullable && !isObject(parentValue)));

  return (
    <details
      className="border-border bg-surface rounded-md border p-3"
      open={isEnabled && !nullable}
    >
      <summary className="cursor-pointer text-sm font-semibold">
        {label}
        <span className="text-text-secondary ml-2 text-xs font-normal">
          ({humanize(group.key)})
        </span>
      </summary>
      <div className="mt-3 grid gap-4">
        {blocked ? (
          <p className="text-text-secondary text-xs">Enable {groupLabel(parent.resolved)} first.</p>
        ) : linked ? (
          <ReadOnlyField
            id={id}
            name={group.key}
            property={group.property}
            source={path.length === 1 ? (context.inputs[group.key] ?? null) : null}
          />
        ) : (
          <>
            {nullable ? (
              <label className="flex items-center gap-2 text-sm" htmlFor={`${id}.enabled`}>
                <input
                  checked={isEnabled}
                  className="accent-primary size-4"
                  id={`${id}.enabled`}
                  onChange={(event) =>
                    onChange(event.target.checked ? seedDefaults(properties, context.defs) : null)
                  }
                  type="checkbox"
                />
                Enable {label}
              </label>
            ) : null}
            {isEnabled || !nullable ? (
              <ObjectFields
                context={context}
                flat
                onChange={onChange}
                path={path}
                properties={properties}
                required={required}
                value={isObject(value) ? value : {}}
              />
            ) : null}
          </>
        )}
      </div>
    </details>
  );
}

// Free-form settings are typed as JSON; only a parsable value is passed on, so a
// half-typed one never reaches the config.
function JsonField({ id, value, cleared, onChange }: JsonFieldProps) {
  const [text, setText] = useState(
    value === undefined || value === null ? "" : JSON.stringify(value),
  );
  const [isInvalid, setIsInvalid] = useState(false);

  return (
    <div className="grid gap-1">
      <input
        aria-invalid={isInvalid}
        className={`${inputClassName} font-mono`}
        id={id}
        onChange={(event) => {
          const nextText = event.target.value;
          setText(nextText);

          if (nextText.trim() === "") {
            setIsInvalid(false);
            onChange(cleared);
            return;
          }

          try {
            onChange(JSON.parse(nextText));
            setIsInvalid(false);
          } catch {
            setIsInvalid(true);
          }
        }}
        placeholder="JSON, e.g. [1, 2]"
        type="text"
        value={text}
      />
      {isInvalid ? <p className="text-xs text-red-700">Not valid JSON yet.</p> : null}
    </div>
  );
}
