import { ApiError, getJson, postJson } from "../../api/manta";
import type {
  CreateProjectResponse,
  CreateRunResponse,
  DefaultProject,
  GetRunLogsResponse,
  GetRunResponse,
} from "./types";

const defaultProjectPayload = {
  name: "My First Project",
  description: "Default project for guest user, first time visit.",
};

const defaultRunPayload = {
  num_pi_digits: 10_000,
};

const defaultProjectSessionStorageKey = "manta.defaultProjectUuid";

export async function getOrCreateDefaultProject(): Promise<DefaultProject> {
  const cachedProjectUuid = window.sessionStorage.getItem(defaultProjectSessionStorageKey);

  if (cachedProjectUuid !== null) {
    return { uuid: cachedProjectUuid, wasCached: true };
  }

  const project = await postJson<CreateProjectResponse>("/v1/projects", defaultProjectPayload);
  window.sessionStorage.setItem(defaultProjectSessionStorageKey, project.uuid);

  return { uuid: project.uuid, wasCached: false };
}

export async function createRun(project: DefaultProject) {
  try {
    return await postJson<CreateRunResponse>("/v1/runs", {
      project_uuid: project.uuid,
      num_pi_digits: defaultRunPayload.num_pi_digits,
    });
  } catch (error) {
    if (project.wasCached && error instanceof ApiError && error.status === 404) {
      window.sessionStorage.removeItem(defaultProjectSessionStorageKey);
    }

    throw error;
  }
}

export function getRun(runId: string) {
  return getJson<GetRunResponse>(`/v1/runs/${runId}`);
}

export function getRunLogs(runId: string) {
  return getJson<GetRunLogsResponse>(`/v1/runs/${runId}/logs`);
}
