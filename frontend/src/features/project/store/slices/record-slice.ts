import {
  connectionStatus,
  onConnectionStatus,
  reconnectRecord,
  setRecordCatalog,
} from "../../lib/record-server/client";
import {
  getCarriers,
  getEntityCounts,
  getLocationZones,
  getLocations,
  getMapBranches,
  openRecord,
  getRegions,
  getScenarioChanges,
  getScenarioChangeValues,
} from "../../lib/record-server/queries";
import { getRecordCatalogue } from "../../../home/lib/record-server";
import { initialScenario, scenarioCatalog, writeScenarioToUrl } from "../../lib/record-scenarios";
import type { RecordInfo } from "../../lib/record-server/types";
import {
  NODAL,
  type ProjectStoreGet,
  type ProjectStoreSet,
  type LoadedRecord,
  type RecordItem,
  type Resolution,
} from "../types";

type ScenarioParts = Omit<LoadedRecord, "info" | "scenarioChanges">;

// What differs per scenario: read from its catalog, which every later query
// reads too.
async function fetchScenario(info: RecordInfo, scenario: string | null): Promise<ScenarioParts> {
  setRecordCatalog(scenarioCatalog(info, scenario));
  const [carriers, entityCounts, locations, zones, branches, regions, changes] = await Promise.all([
    getCarriers(),
    getEntityCounts(),
    getLocations(),
    getLocationZones(),
    getMapBranches(),
    getRegions(),
    scenario ? getScenarioChangeValues(scenario) : Promise.resolve(new Map()),
  ]);
  return {
    carriers: Object.fromEntries(carriers.map((carrier) => [carrier.carrier, carrier])),
    entityCounts,
    locations,
    zones,
    branches,
    regions,
    scenario,
    changes,
  };
}

// A project's record, on the scenario the URL names, else its base case. A
// project that names no record (made before records could be chosen) opens
// the server's default one.
async function fetchRecord(id: string | null): Promise<LoadedRecord> {
  const recordId = id ?? (await getRecordCatalogue()).default;
  if (!recordId) throw new Error("The record server has no records.");
  const info = await openRecord(recordId);
  const parts = await fetchScenario(info, initialScenario(info));
  // Every catalog of the record holds all its scenarios' changes.
  return { info, scenarioChanges: await getScenarioChanges(), ...parts };
}

export function createRecordSlice(set: ProjectStoreSet, get: ProjectStoreGet) {
  onConnectionStatus((status) => set({ connectionStatus: status }));
  return {
    connectionStatus: connectionStatus(),
    // Restores the link and keeps what's loaded; loads the record only if it
    // never loaded.
    reconnect: () => {
      reconnectRecord()
        .then(() => {
          if (get().recordStatus === "error") get().loadRecord(get().recordRequest ?? null);
        })
        .catch((error: unknown) =>
          console.error("Failed to reconnect to the record server", error),
        );
    },

    record: null,
    recordStatus: "idle" as const,
    recordError: null,
    recordRequest: undefined,
    // Loads a project's record; entering another project with the same record
    // keeps what's loaded.
    loadRecord: (id: string | null) => {
      const { recordStatus, recordRequest } = get();
      if (id === recordRequest && (recordStatus === "loading" || recordStatus === "ready")) return;
      // Nothing of the previous record carries over.
      set({
        recordRequest: id,
        recordStatus: "loading",
        recordError: null,
        record: null,
        switchingScenario: null,
        selectedItem: null,
        itemDrawer: null,
        tableDrawer: null,
        resolution: NODAL,
      });
      fetchRecord(id)
        .then((record) => {
          if (get().recordRequest !== id) return;
          writeScenarioToUrl(record.info, record.scenario);
          set({ record, recordStatus: "ready" });
        })
        .catch((error: unknown) => {
          console.error("Failed to load the record", error);
          if (get().recordRequest !== id) return;
          set({
            recordStatus: "error",
            recordError: error instanceof Error ? error.message : String(error),
          });
        });
    },

    switchingScenario: null,
    showScenario: (name: string) => {
      const { record, switchingScenario } = get();
      if (!record || name === (switchingScenario ?? record.scenario)) return;
      set({ switchingScenario: name });
      fetchScenario(record.info, name)
        .then((parts) => {
          const current = get().record;
          if (get().switchingScenario !== name || !current) return;
          writeScenarioToUrl(current.info, name);
          set({ record: { ...current, ...parts }, switchingScenario: null });
        })
        .catch((error: unknown) => {
          console.error(`Failed to load the scenario ${name}`, error);
          if (get().switchingScenario !== name) return;
          // Back to the scenario still shown.
          const current = get().record;
          if (current) setRecordCatalog(scenarioCatalog(current.info, current.scenario));
          set({ switchingScenario: null });
        });
    },

    resolution: NODAL,
    setResolution: (resolution: Resolution) => set({ resolution, selectedItem: null }),

    selectedItem: null,
    selectItem: (item: RecordItem | null) => set({ selectedItem: item }),
    itemDrawer: null,
    openItemDrawer: (item: RecordItem) =>
      set({ itemDrawer: item, selectedItem: item, isNewScenarioDrawerOpen: false }),
    closeItemDrawer: () => set({ itemDrawer: null }),
  };
}
