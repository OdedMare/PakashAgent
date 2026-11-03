"use client";

import { CrewStage } from "@/components/Crew";
import { ChangesPanel } from "@/components/Management/ChangesPanel";
import { activeEmployees } from "@/components/Management";
import { Stats } from "@/components/Management/Stats";
import { useManagement } from "@/components/Management/useManagement";

export type Tool = "stats" | "changes";

/** The משמרת's own statistics and changes, on the מכלול screen.
 *
 *  Not copies: the same `Stats` and `ChangesPanel` the משמרת's commander
 *  uses, over the same routes. The מכלול screen opened this משמרת on the
 *  commander's session before mounting this (`enterComplexTeam`), so every
 *  read and write here is that משמרת's and nobody else's — and every write
 *  is told to its commander like any other (D43). Keyed by the משמרת, so
 *  switching to another starts clean. The agent is not here: it is the
 *  drawer beside the board, which speaks to every משמרת without entering. */
export function UnitTools({
  tool,
  onPrepare,
}: {
  tool: Tool;
  /** The changes page's picks, to become a plan in this משמרת's chat. */
  onPrepare: (message: string) => void;
}) {
  const state = useManagement();
  const overview = state.overview;

  if (!overview) {
    return <CrewStage label="טוען את המשמרת…" />;
  }

  return tool === "stats" ? (
    <div className="manager-overview-flow">
      <Stats overview={overview} expanded />
    </div>
  ) : (
    <div className="cmd-changes">
      <ChangesPanel
        employees={overview.employees}
        activeEmployees={activeEmployees(overview.employees, overview.today ?? "")}
        shifts={overview.shifts}
        today={overview.today ?? ""}
        rotationMode={overview.profile?.workplace?.rotation_mode}
        dayCycles={overview.profile?.workplace?.day_cycles}
        disabled={state.busy}
        onSaveProfile={state.saveProfile}
        onPreviewDeparture={state.previewDeparture}
        onDepart={state.depart}
        onPrepare={onPrepare}
      />
    </div>
  );
}
