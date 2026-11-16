/**
 * Settings of which exactly one must be set, per block.
 *
 * Blocks enforce these in code (a pydantic validator), so neither the catalogue's JSON
 * schema nor the backend's config check knows them: a config that breaks one is
 * accepted and only fails minutes later when the block runs.
 */
export const exactlyOneOf: Record<string, string[][]> = {
  cluster_time: [["segments", "n_hours"]],
};

function isSet(value: unknown): boolean {
  return value !== undefined && value !== null;
}

/** The settings that cannot be edited now because another of their group is set. */
export function blockedSettings(groups: string[][], value: Record<string, unknown>): Set<string> {
  const blocked = new Set<string>();

  for (const group of groups) {
    const setKey = group.find((key) => isSet(value[key]));

    if (setKey !== undefined) {
      group.filter((key) => key !== setKey).forEach((key) => blocked.add(key));
    }
  }

  return blocked;
}

/** One message per group that does not have exactly one setting set, on its first setting. */
export function exactlyOneErrors(
  groups: string[][],
  value: Record<string, unknown>,
): { path: string; message: string }[] {
  return groups
    .filter((group) => group.filter((key) => isSet(value[key])).length !== 1)
    .map((group) => ({
      path: group[0],
      message: `Set exactly one of ${group.join(" or ")}`,
    }));
}
