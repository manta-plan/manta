import { serverName, serverQuery } from "../project/lib/record-server/client";
import type { EntityCount, Manifest } from "../project/lib/record-server/types";

/**
 * What the open project's data contains, as POST /v1/chat/messages takes it:
 * names only, never values. The backend puts them into the model's
 * instructions, so that the model can write a query over them.
 */
export interface ChatRecord {
  components: { ctype: string; carriers: string[] }[];
  attributes: { name: string; unit: string; subject: string; series: boolean }[];
}

// The backend's own patterns (ChatRecord in chat_request.py). It refuses a
// request with any other name, so those are left out here.
const NAME = /^[A-Za-z0-9_]{1,40}$/;
const LABEL = /^[A-Za-z0-9_.+/%\- ]{0,40}$/;

// What an attribute's values belong to: the first of these among its dims,
// as the record server decides it (SUBJECTS in manta_views.py).
const SUBJECTS = ["entity", "connection", "bus", "carrier", "sub_network", "period", "snapshot"];

export function toChatRecord(
  entityCounts: EntityCount[],
  manifest: Manifest,
  attributeNames: string[],
): ChatRecord {
  const carriers = new Map<string, string[]>();
  for (const { ctype, carrier } of entityCounts) {
    if (!NAME.test(ctype)) continue;
    const list = carriers.get(ctype) ?? [];
    if (carrier && LABEL.test(carrier)) list.push(carrier);
    carriers.set(ctype, list);
  }

  const attributes: ChatRecord["attributes"] = [];
  for (const name of attributeNames) {
    const spec = manifest.attributes[name];
    const subject = spec && SUBJECTS.find((dim) => spec.dims.includes(dim));
    if (!subject || !NAME.test(name)) continue;
    attributes.push({
      name,
      unit: spec.unit && LABEL.test(spec.unit) ? spec.unit : "",
      subject,
      series: subject !== "snapshot" && spec.dims.includes("snapshot"),
    });
  }

  return {
    components: [...carriers].map(([ctype, list]) => ({ ctype, carriers: list })),
    attributes,
  };
}

/** The attributes the active scenario has values for; the manifest lists many more. */
export async function loadAttributeNames(): Promise<string[]> {
  const rows = await serverQuery<{ attribute: string }>(
    `SELECT DISTINCT attribute FROM ${serverName("manta.attribute_summary")} ORDER BY attribute`,
  );
  return rows.map((row) => row.attribute);
}
