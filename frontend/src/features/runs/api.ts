import { ApiError, getJson, postJson } from "../../api/manta";
import { decodeTokenClaims, getAccessToken } from "../auth/session";
import type { PlaybookConfig } from "../../utils/playbookTypes";
import type {
  CreateProjectResponse,
  CreateRunResponse,
  DataRecordChoice,
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

// Kept in localStorage, per user (project UUIDs are owned by one user), and not wiped on
// login or logout. The backend has no endpoint listing a user's projects, so forgetting it
// would create a new, empty project (without the example data stores) every time.
function defaultProjectStorageKey(): string | null {
  const accessToken = getAccessToken();
  const claims = accessToken === null ? null : decodeTokenClaims(accessToken);

  return claims === null ? null : `manta.defaultProjectUuid.${claims.sub}`;
}

export function getCachedDefaultProject(): DefaultProject | null {
  const key = defaultProjectStorageKey();
  const cachedProjectUuid = key === null ? null : window.localStorage.getItem(key);

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
  const key = defaultProjectStorageKey();

  if (key !== null) {
    window.localStorage.setItem(key, project.uuid);
  }

  return { uuid: project.uuid, wasCached: false };
}

// Forgets the cached project only when the backend says the project itself is gone. Other
// 404s (e.g. "Revision ... not found") must keep it: forgetting it would create a new,
// empty project on the next request.
function forgetMissingProject(project: DefaultProject, error: unknown) {
  if (
    project.wasCached &&
    error instanceof ApiError &&
    error.status === 404 &&
    error.message.startsWith(`Project ${project.uuid} `)
  ) {
    const key = defaultProjectStorageKey();

    if (key !== null) {
      window.localStorage.removeItem(key);
    }
  }
}

type CreateRunOptions = {
  playbook: string;
  config: PlaybookConfig;
  dataRecord: DataRecordChoice;
};

// The bucket the backend stores projects in (S3_BUCKET in its env).
const storageBucket = "manta";

export async function createRun(project: DefaultProject, options: CreateRunOptions) {
  try {
    return await postJson<CreateRunResponse>("/v1/runs", {
      project_uuid: project.uuid,
      playbook: { name: options.playbook, config: options.config },
      data_record: {
        store_url: `s3://${storageBucket}/${project.uuid}/${options.dataRecord.name}`,
        revision_uuid: options.dataRecord.revision_uuid,
      },
    });
  } catch (error) {
    forgetMissingProject(project, error);

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
    forgetMissingProject(project, error);

    throw error;
  }
}

export async function getRunSummary(project: DefaultProject) {
  try {
    const searchParams = new URLSearchParams({ project_uuid: project.uuid });
    return await getJson<GetRunSummaryResponse>(`/v1/runs/summary?${searchParams.toString()}`);
  } catch (error) {
    forgetMissingProject(project, error);

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
