export type RunStatus = "Running" | "Completed" | "Failed" | "Queued" | "Unknown";

export type CreateProjectResponse = {
  uuid: string;
  name: string;
  description: string | null;
  created_at: string;
};

export type CreateRunResponse = {
  uuid: string;
  project_uuid: string;
  created_at: string;
};

export type GetRunResponse = {
  uuid: string;
  project_uuid: string | null;
  status: string;
  created_at: string;
};

export type ListRunsResponse = {
  items: GetRunResponse[];
  total: number;
  limit: number;
  offset: number;
};

export type GetRunLogsResponse = {
  uuid: string;
  logs: string[];
  run_status: string;
};

export type RunListItem = {
  id: string;
  name: string;
  playbook: string;
  status: RunStatus;
  startedAt: string;
  durationSeconds: number | null;
  trigger: string;
  owner: string;
};

export type ExpandedRunState = {
  isLoading: boolean;
  error: string | null;
  detail: GetRunResponse | null;
  logs: GetRunLogsResponse | null;
};

export type DefaultProject = {
  uuid: string;
  wasCached: boolean;
};
