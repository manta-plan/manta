import { useLocation } from "wouter";
import { HomeLayout } from "../features/home/components/home-layout";
import { getHomeRoute } from "../features/home/routes";

// The landing page after sign in: a sidebar of sections (projects, data
// catalog) around the active section.
export function HomePage() {
  const [location] = useLocation();
  const ActiveSection = getHomeRoute(location).Component;

  return (
    <HomeLayout>
      <ActiveSection />
    </HomeLayout>
  );
}
