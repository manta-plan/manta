import type { JsonObject } from "./playbookFormTypes";

export function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A copy of `object` with `key` set, or removed when `value` is undefined. */
export function withKey(object: JsonObject, key: string, value: unknown): JsonObject {
  const next = { ...object };

  if (value === undefined) {
    delete next[key];
  } else {
    next[key] = value;
  }

  return next;
}

/** A copy of `object` with the value at `path` set, creating objects on the way. */
export function setIn(object: JsonObject, path: string[], value: unknown): JsonObject {
  const [head, ...rest] = path;

  if (rest.length === 0) {
    return withKey(object, head, value);
  }

  const child = object[head];

  return withKey(object, head, setIn(isObject(child) ? child : {}, rest, value));
}
