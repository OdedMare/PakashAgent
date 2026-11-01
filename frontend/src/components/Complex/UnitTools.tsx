"use client";

import { useCallback } from "react";

import { CrewStage } from "@/components/Crew";
import { AgentChat } from "@/components/Management/AgentChat";
import { ChangesPanel } from "@/components/Management/ChangesPanel";
import { chatStarters } from "@/components/Management/chatStarters";
import { activeEmployees } from "@/components/Management";
import { Stats } from "@/components/Management/Stats";
import { useManagement } from "@/components/Management/useManagement";
import { useManagerChat } from "@/components/Management/useManagerChat";

export type Tool = "agent" | "stats" | "changes";

/** The משמרת's own agent, statistics and changes, on the מכלול screen.
 *
 *  Not copies: the same `AgentChat`, `Stats` and `ChangesPanel` the משמרת's
 *  commander uses, over the same routes. The מכלול screen opened this
 *  משמרת on the commander's session before mounting this (`enterComplexTeam`),
 *  so every read and write here is that משמרת's and nobody else's — and
 *  every write is told to its commander like any other (D43). Keyed by the
 *  משמרת, so switching to another starts clean. */
export function UnitTools({
  unitId,
  tool,
  onTool,
}: {
  unitId: string;
  tool: Tool;
  onTool: (tool: Tool) => void;
}) {
  const state = useManagement();
  const { refresh } = state;
  const onApplied = useCallback(async () => {
    await refresh(true);
  }, [refresh]);
  const agent = useManagerChat(unitId, state.focusedScheduleId, state.focusedWeek, "", onApplied);
  const overview = state.overview;

  if (!overview) {
    return <CrewStage label="טוען את המשמרת…" />;
  }

  return (
    <>
      <div className={`manager-drawer-content is-conversation cmd-chat${tool === "agent" ? "" : " is-hidden"}`}>
        <AgentChat
          agent={agent}
          hidden={tool !== "agent"}
          visibleWeek={state.focusedWeek}
          employees={overview.employees.map((person) => String(person.name ?? "")).filter(Boolean)}
          starters={chatStarters({ warnings: overview.schedule?.warnings ?? [], requests: [], focusDate: "" })}
          boardBusy={state.busy}
          onPreview={() => undefined}
          onOpenReceipt={() => undefined}
        />
      </div>

      {tool === "stats" ? (
        <div className="manager-overview-flow">
          <Stats overview={overview} expanded />
        </div>
      ) : null}

      {tool === "changes" ? (
        <div className="cmd-changes">
          <ChangesPanel
            employees={overview.employees}
            activeEmployees={activeEmployees(overview.employees, overview.today ?? "")}
            shifts={overview.shifts}
            today={overview.today ?? ""}
            rotationMode={overview.profile?.workplace?.rotation_mode}
            dayCycles={overview.profile?.workplace?.day_cycles}
            disabled={agent.busy || agent.working}
            onSaveProfile={state.saveProfile}
            onPreviewDeparture={state.previewDeparture}
            onDepart={state.depart}
            onPrepare={(message) => {
              // The picks become a plan in the משמרת's conversation, where
              // approving it is the one write path (D12) — as inside it.
              onTool("agent");
              void agent.send(message);
            }}
          />
        </div>
      ) : null}
    </>
  );
}
