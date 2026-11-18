import type { InspectionCanvas } from "../data/inspections";
import type { WidgetSetItem } from "./widget-sets";

const PROJECT_INSPECTIONS_STORAGE_KEY = "manta-project-inspections-v1";
// Saved widget sets from before they merged into inspections.
const LEGACY_WIDGET_SETS_STORAGE_KEY = "manta-project-widget-sets-v1";

function readStored<T>(key: string): Record<string, T[]> {
  if (typeof localStorage === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(key) ?? "{}") as Record<string, T[]>;
  } catch {
    return {};
  }
}

// Turns a project's saved widget sets into inspections, once.
function migrateWidgetSets(projectId: string, inspections: InspectionCanvas[]): InspectionCanvas[] {
  const legacy = readStored<{ id: string; name: string; items: WidgetSetItem[] }>(
    LEGACY_WIDGET_SETS_STORAGE_KEY,
  );
  const widgetSets = legacy[projectId];
  if (!widgetSets) return inspections;
  const migrated = [
    ...inspections,
    ...widgetSets
      .filter((set) => !inspections.some((inspection) => inspection.id === set.id))
      .map((set) => ({ id: set.id, name: set.name, description: "", items: set.items })),
  ];
  delete legacy[projectId];
  localStorage.setItem(LEGACY_WIDGET_SETS_STORAGE_KEY, JSON.stringify(legacy));
  saveProjectInspections(projectId, migrated);
  return migrated;
}

export function loadProjectInspections(projectId: string): InspectionCanvas[] {
  // Inspections from before they held widgets start empty.
  const inspections = (
    readStored<InspectionCanvas>(PROJECT_INSPECTIONS_STORAGE_KEY)[projectId] ?? []
  ).map((inspection) => ({ ...inspection, items: inspection.items ?? [] }));
  return migrateWidgetSets(projectId, inspections);
}

export function saveProjectInspections(projectId: string | null, inspections: InspectionCanvas[]) {
  if (!projectId || typeof localStorage === "undefined") return;
  const stored = readStored<InspectionCanvas>(PROJECT_INSPECTIONS_STORAGE_KEY);
  stored[projectId] = inspections;
  localStorage.setItem(PROJECT_INSPECTIONS_STORAGE_KEY, JSON.stringify(stored));
}

export function removeProjectInspections(projectId: string) {
  if (typeof localStorage === "undefined") return;
  for (const key of [PROJECT_INSPECTIONS_STORAGE_KEY, LEGACY_WIDGET_SETS_STORAGE_KEY]) {
    const stored = readStored<unknown>(key);
    if (!(projectId in stored)) continue;
    delete stored[projectId];
    localStorage.setItem(key, JSON.stringify(stored));
  }
}
