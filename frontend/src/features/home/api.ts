import { deleteRequest, getJson, patchJson, postJson } from "../../api/manta";
import type { CreateProjectResponse } from "../runs/types";

export type ProjectResponse = CreateProjectResponse & { updated_at: string };

export type ListProjectsResponse = {
  items: ProjectResponse[];
  total: number;
  limit: number;
  offset: number;
};

// The backend allows at most 100 projects per page.
export function listProjects(limit = 100, offset = 0) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return getJson<ListProjectsResponse>(`/v1/projects?${params.toString()}`);
}

export function updateProject(projectUuid: string, name: string, description: string) {
  return patchJson<ProjectResponse>(`/v1/projects/${projectUuid}`, {
    name,
    // The backend clears the description when it is sent as null.
    description: description.trim() || null,
  });
}

export function deleteProject(projectUuid: string) {
  return deleteRequest(`/v1/projects/${projectUuid}`);
}

export function createProject(name: string, description: string) {
  return postJson<CreateProjectResponse>("/v1/projects", {
    name,
    // An empty box means no description, which the backend stores as null.
    description: description.trim() || null,
  });
}
