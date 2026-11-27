// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import type { PlaybookConfig } from "../../utils/playbookTypes";

export type RunStatus = string;

export type CreateProjectResponse = {
  uuid: string;
  name: string;
  description: string | null;
  created_at: string;
};

/** A data record to start a run from: a store's name within the project, and the revision. */
export type DataRecordChoice = {
  name: string;
  revision_uuid: string;
};

export type CreateRunResponse = {
  uuid: string;
  project_uuid: string;
  created_at: string;
};

export type GetRunResponse = {
  uuid: string;
  project_uuid: string;
  playbook: string;
  status: string;
  created_at: string;
  /** The settings the run was started with. Read-only here; absent when the backend omits it. */
  config?: PlaybookConfig | null;
};

export type ListRunsResponse = {
  items: GetRunResponse[];
  total: number;
  limit: number;
  offset: number;
  summary: GetRunSummaryResponse;
};

export type GetRunSummaryResponse = {
  total: number;
  statuses: Record<string, number>;
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

/**
 * A run that has been set up but not started. The backend has no draft, so it
 * lives in the runs store and in the browser's localStorage (see draft-storage.ts);
 * Start sends it as a run and removes it.
 */
export type RunDraft = {
  id: string;
  /** The project route it was created in. */
  projectId: string;
  playbook: string;
  dataRecord: DataRecordChoice;
  scenarioId: string | null;
  scenarioLabel: string | null;
  config: PlaybookConfig;
  createdAt: string;
};
