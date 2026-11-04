import { useLocation } from "wouter";
import { HomeLayout } from "../features/home/components/home-layout";
import { getHomeRoute } from "../features/home/routes";
import { PlaybookDetailSection } from "../features/home/sections/playbook-detail-section";

// The landing page after sign in: a sidebar of sections (projects, data
// catalog, playbooks, infrastructure, settings) around the active section.
export function HomePage() {
  const [location] = useLocation();
  const isPlaybookDetail = location.startsWith("/playbook/");
  const ActiveSection = getHomeRoute(location).Component;

  return (
    <HomeLayout isPlaybookDetail={isPlaybookDetail}>
      {isPlaybookDetail ? <PlaybookDetailSection /> : <ActiveSection />}
    </HomeLayout>
  );
}
