import type { ReactNode } from "react";
import { Link, useLocation } from "wouter";
import { LuLogOut, LuMoon, LuSun } from "react-icons/lu";
import { FaFly } from "react-icons/fa";
import { useAppStore } from "../store";
import { clearSession, useSessionUser } from "../../auth/session";
import { MantaLogo } from "./manta-logo";
import { FeedbackButton } from "./feedback-dialog";
import { GradientWashBackground } from "./gradient-wash-background";
import { NewProjectDrawer } from "./new-project-drawer";
import { RenameProjectDrawer } from "./rename-project-drawer";
import { HOME_ROUTES } from "../routes";
import { startHomeTour } from "../lib/tours";

function initials(name: string) {
  return name
    .split(/[\s._-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

interface HomeLayoutProps {
  children: ReactNode;
  isPlaybookDetail: boolean;
}

export function HomeLayout({ children, isPlaybookDetail }: HomeLayoutProps) {
  const [location] = useLocation();
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  // The router only renders this layout for signed-in users, and signing out
  // sends them back to the login page.
  const username = useSessionUser()?.username ?? "";

  return (
    <div className="bg-surface-900 flex h-svh w-full flex-col">
      <header className="border-surface-600 bg-surface-800 flex h-11 shrink-0 items-center justify-between border-b px-4">
        <MantaLogo />
        <div className="flex items-center gap-1">
          <button
            onClick={startHomeTour}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-7 w-7 items-center justify-center rounded"
            aria-label="Start tour"
            title="Start tour"
          >
            <FaFly size={15} />
          </button>
          <button
            onClick={toggleTheme}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-7 w-7 items-center justify-center rounded"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <LuMoon size={15} /> : <LuSun size={15} />}
          </button>
          <FeedbackButton />
          <button
            onClick={clearSession}
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-7 items-center gap-1.5 rounded px-2 text-[12px] font-medium"
          >
            <LuLogOut size={14} />
            Log out
          </button>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <aside className="border-surface-600 bg-surface-800 flex w-56 shrink-0 flex-col border-r">
          <nav data-tour="home-nav" className="flex flex-col gap-0.5 p-2">
            {HOME_ROUTES.map((item) => {
              const isActive =
                location === item.path || (item.id === "playbooks" && isPlaybookDetail);
              const Icon = item.icon;
              return (
                <Link
                  key={item.id}
                  href={item.path}
                  data-tour={`home-nav-${item.id}`}
                  className={`flex items-center gap-2 rounded px-2.5 py-1.5 text-[13px] font-medium ${
                    isActive
                      ? "bg-accent-600/15 text-accent-400"
                      : "text-surface-300 hover:bg-surface-700 hover:text-surface-50"
                  }`}
                >
                  <Icon size={15} />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="border-surface-600 mt-auto flex items-center gap-2.5 border-t px-4 py-3">
            <div className="bg-accent-600 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[12px] font-semibold text-white">
              {initials(username)}
            </div>
            <div className="min-w-0">
              <div className="text-surface-50 truncate text-[12px] font-medium" title={username}>
                {username}
              </div>
              <div className="text-surface-400 truncate text-[11px]">Signed in</div>
            </div>
          </div>
        </aside>

        {/* overflow-x-hidden matters here: NewProjectDrawer/RenameProjectDrawer
            below are always mounted, sitting off-screen
            via translate-x-full when closed — overflow-auto on both axes would
            let that off-screen geometry count toward this element's scrollable
            width, putting a horizontal scrollbar on every page. */}
        <main
          className={
            isPlaybookDetail
              ? "relative flex-1 overflow-hidden"
              : "relative flex-1 overflow-x-hidden overflow-y-auto"
          }
        >
          {!isPlaybookDetail && <GradientWashBackground />}
          <div className="relative h-full">{children}</div>
          <NewProjectDrawer />
          <RenameProjectDrawer />
        </main>
      </div>
    </div>
  );
}
