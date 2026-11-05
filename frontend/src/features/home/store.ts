import { create } from "zustand";
import { removeProjectInspections } from "../project/lib/project-inspections";
import { removeProjectReports } from "../project/lib/project-reports";
import { removeProjectRuns } from "../project/lib/project-runs";
import { removeProjectScenarios } from "../project/lib/project-scenarios";

export type Theme = "dark" | "light";

export type Project = {
  id: string;
  name: string;
  // The record on the record server the project shows.
  recordId?: string;
  lastModified: string;
  // Set on creation and cleared once the welcome dialog is dismissed. Absent on
  // projects made before it existed, so they never show it.
  showWelcome?: boolean;
};

type HomeState = {
  theme: Theme;
  toggleTheme: () => void;

  projects: Project[];
  addProject: (name?: string, recordId?: string) => Project;
  renameProject: (id: string, name: string) => void;
  dismissProjectWelcome: (id: string) => void;
  removeProject: (id: string) => Promise<void>;

  statusMessage: string;
  setStatusMessage: (message: string) => void;

  isNewProjectDrawerOpen: boolean;
  openNewProjectDrawer: () => void;
  closeNewProjectDrawer: () => void;
  projectToRename: Pick<Project, "id" | "name"> | null;
  openRenameProjectDrawer: (project: Pick<Project, "id" | "name">) => void;
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
    return stored.projects ?? [];
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

// Projects are local to the browser for now: the backend has no project
// listing endpoint yet, so this list is not shared with the runs page.
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
  addProject: (name, recordId) => {
    const project: Project = {
      id: `project-${Date.now()}`,
      name: name?.trim() || `Untitled Project ${get().projects.length + 1}`,
      ...(recordId ? { recordId } : {}),
      lastModified: "Just now",
      showWelcome: true,
    };
    const projects = [project, ...get().projects];
    persistProjects(projects);
    set({ projects });
    return project;
  },
  renameProject: (id, name) => {
    const projectName = name.trim();
    if (!projectName) return;
    const projects = get().projects.map((project) =>
      project.id === id ? { ...project, name: projectName } : project,
    );
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
