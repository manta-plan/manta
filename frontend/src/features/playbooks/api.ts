import { getJson, postJson } from "../../api/manta";
import type {
  ListPlaybooksResponse,
  PlaybookConfig,
  PlaybookDetail,
  ValidatePlaybookConfigResponse,
} from "../../utils/playbookTypes";

export async function listPlaybooks() {
  return getJson<ListPlaybooksResponse>("/v1/playbooks");
}

export async function getPlaybook(playbookName: string) {
  return getJson<PlaybookDetail>(`/v1/playbooks/${encodeURIComponent(playbookName)}`);
}

export async function validatePlaybookConfig(playbookName: string, config: PlaybookConfig) {
  return postJson<ValidatePlaybookConfigResponse>(
    `/v1/playbooks/${encodeURIComponent(playbookName)}/validate`,
    { config },
  );
}
