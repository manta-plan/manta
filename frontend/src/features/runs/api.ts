import { ApiError, getJson, postJson } from "../../api/manta";
import type { PlaybookConfig } from "../../utils/playbookTypes";
import type {
  CreateRunResponse,
  DataRecordChoice,
  GetRunLogsResponse,
  GetRunResponse,
  GetRunSummaryResponse,
  ListRunsResponse,
  RunStatus,
} from "./types";

type CreateRunOptions = {
  playbook: string;
  config: PlaybookConfig;
  dataRecord: DataRecordChoice;
};

// The bucket the backend stores projects in (S3_BUCKET in its env). Set VITE_S3_BUCKET
// when the backend uses another one.
const storageBucket: string = import.meta.env.VITE_S3_BUCKET ?? "manta";

const missingRevisionPattern = /^Revision (\S+) not found in '(.+)'$/;

// The backend refuses a run whose data record revision is missing from the store. Turns that
// into a message the user can act on; any other error is returned unchanged.
export function toFriendlyRunError(error: unknown): unknown {
  if (!(error instanceof ApiError) || error.status !== 404) {
    return error;
  }

  const match = missingRevisionPattern.exec(error.message);

  if (match === null) {
    return error;
  }

  const [, revisionUuid, storeUrl] = match;
  const storeName = storeUrl.split("/").filter(Boolean).pop() ?? storeUrl;

  return new ApiError(
    error.status,
    `The data record "${storeName}" is not available in this project (revision ${revisionUuid}). Please select another data record.`,
  );
}

export async function createRun(projectUuid: string, options: CreateRunOptions) {
  try {
    return await postJson<CreateRunResponse>("/v1/runs", {
      project_uuid: projectUuid,
      playbook: { name: options.playbook, config: options.config },
      data_record: {
        store_url: `s3://${storageBucket}/${projectUuid}/${options.dataRecord.name}`,
        revision_uuid: options.dataRecord.revision_uuid,
      },
    });
  } catch (error) {
    throw toFriendlyRunError(error);
  }
}

type ListRunsParams = {
  limit: number;
  offset: number;
  statuses: RunStatus[];
};

export function listRuns(projectUuid: string, params: ListRunsParams) {
  const searchParams = new URLSearchParams({
    project_uuid: projectUuid,
    limit: String(params.limit),
    offset: String(params.offset),
  });
  params.statuses.forEach((status) => {
    searchParams.append("statuses", status);
  });
  return getJson<ListRunsResponse>(`/v1/runs?${searchParams.toString()}`);
}

export function getRunSummary(projectUuid: string) {
  const searchParams = new URLSearchParams({ project_uuid: projectUuid });
  return getJson<GetRunSummaryResponse>(`/v1/runs/summary?${searchParams.toString()}`);
}

export async function getProjectRun(projectUuid: string, runId: string) {
  try {
    const run = await getRun(runId);

    if (run.project_uuid !== projectUuid) {
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
