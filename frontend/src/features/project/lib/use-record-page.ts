import { useCallback } from "react";
import { useLocation, useParams } from "wouter";
import { getActiveProjectTab, projectRecordPageHref } from "./project-route";

// A level's page opens on the Build and Inspect tabs alike; a link on one
// stays on that tab.

/** The tab the record's pages are on: Inspect there, else Build. */
export function useRecordPageTab(): "build" | "inspect" {
  const [location] = useLocation();
  return getActiveProjectTab(location) === "inspect" ? "inspect" : "build";
}

/** Opens a page of the record on the current tab; no page id opens All entities. */
export function useOpenRecordPage(): (pageId?: string | null) => void {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const tab = useRecordPageTab();
  return useCallback(
    (pageId?: string | null) => navigate(projectRecordPageHref(projectId, tab, pageId)),
    [navigate, projectId, tab],
  );
}

/** The record's page open on the current tab, from the address: null on All entities. */
export function useOpenRecordPageId(): string | null {
  const { detailId } = useParams<{ detailId?: string }>();
  const [location] = useLocation();
  const tab = getActiveProjectTab(location);
  return tab === "build" || tab === "inspect" ? (detailId ?? null) : null;
}
