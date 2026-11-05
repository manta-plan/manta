import { INITIAL_SCENARIOS, type Scenario } from "../data/scenarios";

const PROJECT_SCENARIOS_STORAGE_KEY = "manta-project-scenarios-v1";
const OBSOLETE_SCENARIO_IDS = new Set(["scenario-zonal-result"]);

function defaultScenarios(): Scenario[] {
  return structuredClone(INITIAL_SCENARIOS);
}

function storedScenarios(): Record<string, Scenario[]> {
  if (typeof localStorage === "undefined") return {};
  try {
    return JSON.parse(localStorage.getItem(PROJECT_SCENARIOS_STORAGE_KEY) ?? "{}") as Record<
      string,
      Scenario[]
    >;
  } catch {
    return {};
  }
}

function normalise(scenarios: Scenario[]): Scenario[] {
  return scenarios
    .filter((scenario) => !OBSOLETE_SCENARIO_IDS.has(scenario.id))
    .map((scenario) => ({
      ...scenario,
      mutations: scenario.mutations.map((mutation) => ({
        ...mutation,
        name: mutation.name || mutation.description,
      })),
    }));
}

export function loadProjectScenarios(projectId: string): Scenario[] {
  const scenarios = storedScenarios()[projectId];
  if (!scenarios) return defaultScenarios();
  const normalised = normalise(scenarios);
  if (normalised.length === 0) return defaultScenarios();
  saveProjectScenarios(projectId, normalised);
  return normalised;
}

export function saveProjectScenarios(projectId: string | null, scenarios: Scenario[]) {
  if (!projectId || typeof localStorage === "undefined") return;
  const stored = storedScenarios();
  stored[projectId] = normalise(scenarios);
  localStorage.setItem(PROJECT_SCENARIOS_STORAGE_KEY, JSON.stringify(stored));
}

export function removeProjectScenarios(projectId: string) {
  if (typeof localStorage === "undefined") return;
  const stored = storedScenarios();
  if (!(projectId in stored)) return;
  delete stored[projectId];
  localStorage.setItem(PROJECT_SCENARIOS_STORAGE_KEY, JSON.stringify(stored));
}
