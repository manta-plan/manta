import { ApiError, getJson, postJson } from "../../api/manta";
import type {
  CreateProjectResponse,
  CreateRunResponse,
  DefaultProject,
  GetRunLogsResponse,
  GetRunResponse,
  GetRunSummaryResponse,
  ListRunsResponse,
  RunStatus,
} from "./types";

const defaultProjectPayload = {
  name: "My First Project",
  description: "Default project for guest user, first time visit.",
};

const defaultRunPayload = {
  playbook: "cluster-expand-dispatch",
  // TODO: there is no data-record creation in the frontend yet (file upload,
  // or any other way to point a run at real data). This placeholder satisfies
  // the API shape but doesn't resolve to anything real, so a run created this
  // way won't complete — replace once that functionality exists.
  data_record_url: "s3://manta/placeholder/input.nc",
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
      playbook: defaultRunPayload.playbook,
      data_record_url: defaultRunPayload.data_record_url,
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
  statuses: RunStatus[];
};

export async function listRuns(project: DefaultProject, params: ListRunsParams) {
  try {
    const searchParams = new URLSearchParams({
      project_uuid: project.uuid,
      limit: String(params.limit),
      offset: String(params.offset),
    });
    params.statuses.forEach((status) => {
      searchParams.append("statuses", status);
    });
    return await getJson<ListRunsResponse>(`/v1/runs?${searchParams.toString()}`);
  } catch (error) {
    if (project.wasCached && error instanceof ApiError && error.status === 404) {
      window.sessionStorage.removeItem(defaultProjectSessionStorageKey);
    }

    throw error;
  }
}

export async function getRunSummary(project: DefaultProject) {
  try {
    const searchParams = new URLSearchParams({ project_uuid: project.uuid });
    return await getJson<GetRunSummaryResponse>(`/v1/runs/summary?${searchParams.toString()}`);
  } catch (error) {
    if (project.wasCached && error instanceof ApiError && error.status === 404) {
      window.sessionStorage.removeItem(defaultProjectSessionStorageKey);
    }

    throw error;
  }
}

export async function getProjectRun(project: DefaultProject, runId: string) {
  try {
    const run = await getRun(runId);

    if (run.project_uuid !== project.uuid) {
      return null;
    }

    return run;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      return null;
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
