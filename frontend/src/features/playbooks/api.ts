import { getJson } from "../../api/manta";
import type { ListPlaybooksResponse, PlaybookDetail } from "./types";

export async function listPlaybooks() {
  return getJson<ListPlaybooksResponse>("/v1/playbooks");
}

export async function getPlaybook(playbookId: string) {
  return getJson<PlaybookDetail>(`/v1/playbooks/${playbookId}`);
}
