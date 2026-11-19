import { create } from "zustand";
import { removeProjectInspections } from "../project/lib/project-inspections";
import { removeProjectReports } from "../project/lib/project-reports";
import { removeProjectRuns } from "../project/lib/project-runs";
import { removeProjectScenarios } from "../project/lib/project-scenarios";

export type Theme = "dark" | "light";

export type Project = {
  // The backend project's uuid.
  id: string;
  name: string;
  description?: string;
  // The record on the record server the project shows.
  recordId?: string;
  lastModified: string;
  // Set on creation and cleared once the welcome dialog is dismissed. Absent on
  // projects made before it existed, so they never show it.
  showWelcome?: boolean;
};

export type BackendProject = {
  uuid: string;
  name: string;
  description: string | null;
  updated_at: string;
};

// Projects made before the backend stored them have this id prefix. They only
// exist in the browser and are dropped.
const localProjectIdPrefix = "project-";

export function withoutLocalProjects(projects: Project[]): Project[] {
  return projects.filter((project) => !project.id.startsWith(localProjectIdPrefix));
}

// The backend's projects, keeping the browser-only fields (record, welcome flag) of the
// ones it already knew. Anything not in the backend list is dropped.
export function mergeBackendProjects(
  current: Project[],
  backendProjects: BackendProject[],
): Project[] {
  const localById = new Map(current.map((project) => [project.id, project]));
  return backendProjects.map((backendProject) => {
    const local = localById.get(backendProject.uuid);
    return {
      id: backendProject.uuid,
      name: backendProject.name,
      ...(backendProject.description ? { description: backendProject.description } : {}),
      ...(local?.recordId ? { recordId: local.recordId } : {}),
      lastModified: new Date(backendProject.updated_at).toLocaleString(),
      ...(local?.showWelcome ? { showWelcome: true } : {}),
    };
  });
}

type HomeState = {
  theme: Theme;
  toggleTheme: () => void;

  projects: Project[];
  addProject: (
    name: string,
    recordId: string | undefined,
    backend: { uuid: string; description?: string | null },
  ) => Project;
  syncProjects: (backendProjects: BackendProject[]) => void;
  renameProject: (id: string, name: string, description?: string) => void;
  dismissProjectWelcome: (id: string) => void;
  removeProject: (id: string) => Promise<void>;

  statusMessage: string;
  setStatusMessage: (message: string) => void;

  isNewProjectDrawerOpen: boolean;
  openNewProjectDrawer: () => void;
  closeNewProjectDrawer: () => void;
  projectToRename: Pick<Project, "id" | "name" | "description"> | null;
  openRenameProjectDrawer: (project: Pick<Project, "id" | "name" | "description">) => void;
  closeRenameProjectDrawer: () => void;
};

const themeStorageKey = "manta-plan-theme";
const projectsStorageKey = "manta-local-home-data";

function readInitialTheme(): Theme {
  try {
    return window.localStorage.getItem(themeStorageKey) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

function readInitialProjects(): Project[] {
  try {
    const stored = JSON.parse(window.localStorage.getItem(projectsStorageKey) ?? "{}") as {
      projects?: Project[];
    };
    return withoutLocalProjects(stored.projects ?? []);
  } catch {
    return [];
  }
}

function persistProjects(projects: Project[]) {
  try {
    window.localStorage.setItem(projectsStorageKey, JSON.stringify({ projects }));
  } catch {
    // Storage can be blocked; the projects then only last for this session.
  }
}

// The projects come from the backend (`syncProjects`); the browser keeps a copy to show
// before it answers, plus the record and welcome flag the backend does not store.
export const useAppStore = create<HomeState>((set, get) => ({
  theme: readInitialTheme(),
  toggleTheme: () =>
    set((state) => {
      const next: Theme = state.theme === "dark" ? "light" : "dark";
      try {
        window.localStorage.setItem(themeStorageKey, next);
      } catch {
        // The choice then only lasts for this session.
      }
      return { theme: next };
    }),

  projects: readInitialProjects(),
  addProject: (name, recordId, backend) => {
    const project: Project = {
      id: backend.uuid,
      name: name.trim() || `Untitled Project ${get().projects.length + 1}`,
      ...(backend.description ? { description: backend.description } : {}),
      ...(recordId ? { recordId } : {}),
      lastModified: "Just now",
      showWelcome: true,
    };
    const projects = [project, ...get().projects];
    persistProjects(projects);
    set({ projects });
    return project;
  },
  syncProjects: (backendProjects) => {
    const projects = mergeBackendProjects(get().projects, backendProjects);
    persistProjects(projects);
    set({ projects });
  },
  renameProject: (id, name, description) => {
    const projectName = name.trim();
    if (!projectName) return;
    const projects = get().projects.map((project) => {
      if (project.id !== id) return project;
      // `description` left out keeps the current one; an empty string clears it.
      const { description: current, ...rest } = project;
      const nextDescription = description === undefined ? current : description.trim();
      return {
        ...rest,
        name: projectName,
        ...(nextDescription ? { description: nextDescription } : {}),
      };
    });
    persistProjects(projects);
    set({ projects });
  },
  dismissProjectWelcome: (id) => {
    const projects = get().projects.map((project) =>
      project.id === id ? { ...project, showWelcome: false } : project,
    );
    persistProjects(projects);
    set({ projects });
  },
  removeProject: async (id) => {
    // What the project workspace saved under this project goes with it.
    removeProjectScenarios(id);
    removeProjectRuns(id);
    removeProjectInspections(id);
    removeProjectReports(id);
    const projects = get().projects.filter((project) => project.id !== id);
    persistProjects(projects);
    set({ projects });
  },

  statusMessage: "Ready",
  setStatusMessage: (message) => set({ statusMessage: message }),

  isNewProjectDrawerOpen: false,
  openNewProjectDrawer: () => set({ isNewProjectDrawerOpen: true, projectToRename: null }),
  closeNewProjectDrawer: () => set({ isNewProjectDrawerOpen: false }),
  projectToRename: null,
  openRenameProjectDrawer: (project) =>
    set({ projectToRename: project, isNewProjectDrawerOpen: false }),
  closeRenameProjectDrawer: () => set({ projectToRename: null }),
}));
