import type { DataRecordChoice } from "./types";

// TODO: temporary. The backend has no endpoint listing a project's data record
// stores, so this is the fixed set of example stores every Example project is
// seeded with, and each store's `inputs` revision (see "Example data" in
// backend/README.md). The revision UUIDs belong to the seeded example data, so they
// stop matching if it is re-seeded. Replace with a backend listing once one exists.
// `europe-full-res-2030` is left out: the backend skips it by default for its size.
export const exampleDataRecords: DataRecordChoice[] = [
  { name: "ac-dc-meshed", revision_uuid: "e5f2eacd-ba5c-463c-a663-3017ef904d1d" },
  { name: "model-energy", revision_uuid: "075955d5-fe04-48de-bc6c-75ad873de6c0" },
  { name: "BEL-pre-aggregated", revision_uuid: "c7525fa8-e4da-4569-bbf3-b76669d1a2df" },
  { name: "BEL-pre-aggregated-hourly", revision_uuid: "fc0145a7-3cdf-4c5f-a9c9-ec77a472cb99" },
  {
    name: "BEL-pre-aggregated-incl-patches-incl-results",
    revision_uuid: "4dbf521c-2911-40be-8c6e-b075daa1a8ec",
  },
  { name: "BEL-full-res", revision_uuid: "f910244f-99d2-4ae0-8ba7-a10dbd54f7e0" },
];
