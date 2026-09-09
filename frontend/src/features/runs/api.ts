import { ApiError, getJson, postJson } from "../../api/manta";
import type {
  CreateProjectResponse,
  CreateRunResponse,
  DefaultProject,
  GetRunLogsResponse,
  GetRunResponse,
  ListRunsResponse,
} from "./types";

const defaultProjectPayload = {
  name: "My First Project",
  description: "Default project for guest user, first time visit.",
};

const defaultRunPayload = {
  num_pi_digits: 10_000,
};

const defaultProjectSessionStorageKey = "manta.defaultProjectUuid";

export function getCachedDefaultProject(): DefaultProject | null {
  const cachedProjectUuid = window.sessionStorage.getItem(defaultProjectSessionStorageKey);

  if (cachedProjectUuid === null) {
    return null;
  }

  return { uuid: cachedProjectUuid, wasCached: true };
}

export async function getOrCreateDefaultProject(): Promise<DefaultProject> {
  const cachedProject = getCachedDefaultProject();

  if (cachedProject !== null) {
    return cachedProject;
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

type ListRunsParams = {
  limit: number;
  offset: number;
};

export async function listRuns(project: DefaultProject, params: ListRunsParams) {
  try {
    const searchParams = new URLSearchParams({
      project_uuid: project.uuid,
      limit: String(params.limit),
      offset: String(params.offset),
    });
    return await getJson<ListRunsResponse>(`/v1/runs?${searchParams.toString()}`);
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
