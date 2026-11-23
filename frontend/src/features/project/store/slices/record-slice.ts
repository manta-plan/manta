// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

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
  openRecord,
  getScenarioChanges,
  getScenarioChangeValues,
} from "../../lib/record-server/queries";
import { getRecordCatalogue } from "../../../home/lib/record-server";
import {
  initialScenario,
  isRunResult,
  scenarioCatalog,
  writeScenarioToUrl,
} from "../../lib/record-scenarios";
import type { RecordInfo } from "../../lib/record-server/types";
import { type ProjectStoreGet, type ProjectStoreSet, type LoadedRecord } from "../types";

type ScenarioParts = Omit<LoadedRecord, "info" | "scenarioChanges">;

// The record's info with `name` attached on the server: a run result is
// attached when first shown.
async function withRevisionOpen(info: RecordInfo, name: string | null): Promise<RecordInfo> {
  const revision = info.revisions.find((item) => item.name === name);
  return name && isRunResult(revision) && !revision?.open ? openRecord(info.id, name) : info;
}

// What differs per scenario: read from its catalog, which every later query
// reads too.
async function fetchScenario(info: RecordInfo, scenario: string | null): Promise<ScenarioParts> {
  setRecordCatalog(scenarioCatalog(info, scenario));
  const [carriers, entityCounts, locations, zones, changes] = await Promise.all([
    getCarriers(),
    getEntityCounts(),
    getLocations(),
    getLocationZones(),
    scenario ? getScenarioChangeValues(scenario) : Promise.resolve(new Map()),
  ]);
  return {
    carriers: Object.fromEntries(carriers.map((carrier) => [carrier.carrier, carrier])),
    entityCounts,
    locations,
    zones,
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
  const opened = await openRecord(recordId);
  const scenario = initialScenario(opened);
  const info = await withRevisionOpen(opened, scenario);
  const parts = await fetchScenario(info, scenario);
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
        scenarioChange: null,
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
      withRevisionOpen(record.info, name)
        .then(async (info) => ({ info, parts: await fetchScenario(info, name) }))
        .then(({ info, parts }) => {
          const current = get().record;
          if (get().switchingScenario !== name || !current) return;
          writeScenarioToUrl(info, name);
          set({ record: { ...current, info, ...parts }, switchingScenario: null });
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
  };
}
