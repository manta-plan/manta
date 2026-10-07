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

// TODO: there is no data-record creation in the frontend yet (file upload,
// or any other way to point a run at real data). This placeholder satisfies
// the API shape but doesn't resolve to anything real, so a run created this
// way won't complete — replace once that functionality exists.
const placeholderDataRecordUrl = "s3://manta/placeholder/input.nc";

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

export async function createRun(
  project: DefaultProject,
  _name: string,
  playbookId: string,
  playbookConfig: Record<string, number>[],
) {
  // `_name` isn't part of the API contract yet (no `name` column on `runs`) —
  // kept as a dialog-local label only. `playbookConfig` is one entry per
  // playbook node (only the configured node is ever non-empty, see
  // create-run-dialog.tsx), merged here into the flat config dict the
  // backend expects.
  const config = Object.assign({}, ...playbookConfig);

  try {
    return await postJson<CreateRunResponse>("/v1/runs", {
      project_uuid: project.uuid,
      playbook: playbookId,
      config,
      data_record_url: placeholderDataRecordUrl,
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
