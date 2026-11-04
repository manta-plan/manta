import { LuCpu, LuHardDrive, LuGlobe } from "react-icons/lu";
import { INFRASTRUCTURE_RESOURCES } from "../data/infrastructure-resources";
import { HomeCard, HomeSectionFrame, StatusPill } from "../components/home-primitives";
import { SectionHeader } from "../components/section-header";

const RESOURCE_ICON = {
  compute: LuCpu,
  storage: LuHardDrive,
  region: LuGlobe,
};

export function CloudResourcesSection() {
  return (
    <HomeSectionFrame>
      <SectionHeader
        title="Infrastructure"
        description="Compute, storage, and runtime resources backing your projects."
      />

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {INFRASTRUCTURE_RESOURCES.map((resource) => {
          const Icon = RESOURCE_ICON[resource.kind];
          return (
            <HomeCard key={resource.id}>
              <div className="mb-3 flex items-center justify-between">
                <div className="text-surface-50 flex items-center gap-2">
                  <Icon size={16} className="text-accent-400" />
                  <span className="text-[13px] font-medium">{resource.title}</span>
                </div>
                {"status" in resource && (
                  <StatusPill tone={resource.statusTone ?? "neutral"}>{resource.status}</StatusPill>
                )}
              </div>
              {"usedPercent" in resource && (
                <div className="bg-surface-700 mb-1.5 h-1.5 w-full overflow-hidden rounded-full">
                  <div
                    className="bg-accent-500 h-full rounded-full"
                    style={{ width: `${resource.usedPercent}%` }}
                  />
                </div>
              )}
              <div className="text-surface-300 text-[12px]">{resource.detail}</div>
              <div className="text-surface-500 mt-1 text-[11px]">{resource.meta}</div>
            </HomeCard>
          );
        })}
      </div>
    </HomeSectionFrame>
  );
}
