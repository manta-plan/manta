import type { DataRecordChoice } from "./types";

// TODO: temporary. The backend has no endpoint listing a project's data record
// stores, so this is the fixed set of example stores every Example project is
// seeded with, and each store's `inputs` revision (see "Example data" in
// backend/README.md). The revision UUIDs come from the 2026-11-11 seed; check the
// README table when the data is re-seeded, as they stop matching otherwise. Replace with a backend listing once one exists.
// `europe-full-res-2030` is left out: the backend skips it by default for its size.
export const exampleDataRecords: DataRecordChoice[] = [
  { name: "ac-dc-meshed", revision_uuid: "1bad4cfd-9f32-4675-aa4b-6cd71660cbc1" },
  { name: "model-energy", revision_uuid: "fc70f1c9-1082-46a9-8774-66bd5fad7297" },
  { name: "BEL-pre-aggregated", revision_uuid: "8ff7a95a-8aed-42a3-9acb-a2e36906685f" },
  { name: "BEL-pre-aggregated-hourly", revision_uuid: "8b7175d6-f540-4aa0-98c0-2df460693ff1" },
  {
    name: "BEL-pre-aggregated-incl-patches-incl-results",
    revision_uuid: "9ec88f52-d2d7-4785-9cbb-0c9a1da9b827",
  },
  { name: "BEL-full-res", revision_uuid: "0921e11f-1998-4983-9992-9a2f923ed392" },
];
