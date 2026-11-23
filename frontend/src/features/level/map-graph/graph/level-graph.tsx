import { useLevelPage } from "../../level-page-context";
import { useFocusTarget } from "../map-graph-data";
import { BusSchematic } from "./bus-schematic";
import { NetworkGraph } from "./network-graph";

// The Graph tab: every bus at All locations; one location's schematic at a
// location, a bus (its location, the bus in focus) or an entity (its bus's
// location, the entity in focus).

export function LevelGraph() {
  const { level, scope } = useLevelPage();
  const entity = level.kind === "entity" ? level.entity : null;
  const target = useFocusTarget(scope, entity);

  switch (level.kind) {
    case "all-locations":
      return <NetworkGraph />;
    case "location":
      return <BusSchematic location={level.location} focusBus={null} focusEntity={null} />;
    case "bus":
      return level.location ? (
        <BusSchematic location={level.location} focusBus={level.bus} focusEntity={null} />
      ) : (
        <Note text={`Bus ${level.bus} has no location.`} />
      );
    case "entity":
      if (target.status === "loading") return <Note text="Loading…" />;
      if (target.status === "error")
        return <Note text={`Can't read the entity: ${target.error}`} />;
      return target.data?.location ? (
        <BusSchematic location={target.data.location} focusBus={null} focusEntity={level.entity} />
      ) : (
        <Note text="This entity has no bus at a location." />
      );
    default:
      return (
        <Note text="The graph shows buses. Open a single entity or the Locations tree to use it." />
      );
  }
}

function Note({ text }: { text: string }) {
  return <p className="text-surface-500 p-4 text-[11px]">{text}</p>;
}
