import { LuCloud, LuDatabase, LuFolder, LuSettings, LuWorkflow } from "react-icons/lu";
import type { ComponentType } from "react";
import type { IconType } from "react-icons";
import { ProjectsSection } from "./sections/projects-section";
import { DataCatalogSection } from "./sections/data-catalog-section";
import { PlaybooksSection } from "./sections/playbooks-section";
import { CloudResourcesSection } from "./sections/cloud-resources-section";
import { SettingsSection } from "./sections/settings-section";

export type HomeRouteId = "projects" | "data" | "playbooks" | "infrastructure" | "settings";

export interface HomeRouteDefinition {
  id: HomeRouteId;
  path: string;
  label: string;
  icon: IconType;
  Component: ComponentType;
}

export const HOME_ROUTES: HomeRouteDefinition[] = [
  { id: "projects", path: "/", label: "Projects", icon: LuFolder, Component: ProjectsSection },
  {
    id: "data",
    path: "/data",
    label: "Data Catalog",
    icon: LuDatabase,
    Component: DataCatalogSection,
  },
  {
    id: "playbooks",
    path: "/playbooks",
    label: "Playbooks",
    icon: LuWorkflow,
    Component: PlaybooksSection,
  },
  {
    id: "infrastructure",
    path: "/infrastructure",
    label: "Infrastructure",
    icon: LuCloud,
    Component: CloudResourcesSection,
  },
  {
    id: "settings",
    path: "/settings",
    label: "Settings",
    icon: LuSettings,
    Component: SettingsSection,
  },
];

export function getHomeRoute(path: string) {
  return HOME_ROUTES.find((route) => route.path === path) ?? HOME_ROUTES[0];
}
