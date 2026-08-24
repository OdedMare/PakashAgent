"use client";

import { useState } from "react";

import { Employee } from "@/components/Employee";
import { Interview } from "@/components/Interview";
import { Management } from "@/components/Management";
import { ManualSetup } from "@/components/ManualSetup";

import { Login } from "./Login";
import { MemberArea } from "./MemberArea";
import { useWorkspace } from "./useWorkspace";

/** Chooses the surface for whoever is at the door.
 *
 *  The role comes from the signed session cookie, never from the client, so
 *  this is a render of what the server already decided rather than a check
 *  the browser performs. The backend guards every route independently — a
 *  visitor who forced their way past this component would still be refused by
 *  `Guards.boss()` on the API. */
export function Workspace({ memberToken }: { memberToken?: string }) {
  const state = useWorkspace();
  const { workspace } = state;

  // The first `me` call has not answered yet. Rendering the login screen here
  // would flash it at a boss who is already signed in.
  if (workspace === undefined) {
    return <div className="workspace-gate" aria-busy="true" />;
  }

  if (workspace === null) {
    return (
      <Login
        busy={state.busy}
        error={state.error}
        onLogin={state.login}
        onCreate={state.create}
        onDismissError={state.clearError}
      />
    );
  }

  if (workspace.role === "member") {
    return <MemberSurface state={state} workspace={workspace} />;
  }

  // An employee who signed in personally. The role is on the signed cookie,
  // so this is a render of what the server decided — every route the personal
  // area calls is guarded independently by `Guards.employee()`.
  if (workspace.role === "employee") {
    return <Employee onLeave={state.logout} />;
  }

  return <BossSurface state={state} workspace={workspace} />;
}

/** The manager's side: the interview until the workplace is taught, the
 *  management area after.
 *
 *  The profile is what switches them. It is the interview's durable result,
 *  so its presence means the workplace has been taught and there is
 *  something to schedule against — which is exactly the condition the
 *  management area needs. A manager can still reopen the interview to
 *  re-teach the workplace, and `reinterview` is that door; it is deliberately
 *  an explicit choice rather than something the app decides for them, since
 *  re-running the interview replaces the profile everything downstream reads. */
function BossSurface({
  state,
  workspace,
}: {
  state: ReturnType<typeof useWorkspace>;
  workspace: NonNullable<ReturnType<typeof useWorkspace>["workspace"]>;
}) {
  const [setupMode, setSetupMode] = useState<"interview" | "manual" | null>(null);
  const [buildAfterInterview, setBuildAfterInterview] = useState(false);
  const taught = Boolean(workspace.profile);

  if (setupMode === "manual") {
    return (
      <ManualSetup
        workspace={workspace}
        onCancel={taught ? () => setSetupMode(null) : undefined}
        onDone={async () => {
          setSetupMode(null);
          await state.refresh();
        }}
      />
    );
  }

  if (taught && setupMode !== "interview") {
    return (
      <Management
        workspace={workspace}
        busy={state.busy}
        onLogout={state.logout}
        onRotateLink={state.rotateLink}
        onOpenInterview={() => setSetupMode("interview")}
        onOpenManualSetup={() => setSetupMode("manual")}
        autoGenerate={buildAfterInterview}
        onAutoGenerateStarted={() => setBuildAfterInterview(false)}
      />
    );
  }

  // Always supplied now, taught or not. `refresh` re-reads the profile the
  // interview just wrote, so a first interview ended early lands on a
  // management area that already knows what it was given — without it,
  // `taught` is still false from the last fetch and the router sends the
  // manager straight back into the interview they just left.
  return (
    <Interview
      workspace={workspace}
      busy={state.busy}
      onLogout={state.logout}
      onRotateLink={state.rotateLink}
      onDone={async () => {
        setSetupMode(null);
        await state.refresh();
      }}
      onBuild={async () => {
        setBuildAfterInterview(true);
        setSetupMode(null);
        await state.refresh();
      }}
      onManualSetup={() => setSetupMode("manual")}
    />
  );
}

/** The team view, with a door into the personal area.
 *
 *  Two surfaces rather than one because they authenticate differently: the
 *  share link grants the read-only roster (D10), and claiming a name grants a
 *  personal identity on top of it (D14). Keeping the roster reachable without
 *  claiming is deliberate — a team that does not want identities is not
 *  forced into them. */
function MemberSurface({
  state,
  workspace,
}: {
  state: ReturnType<typeof useWorkspace>;
  workspace: NonNullable<ReturnType<typeof useWorkspace>["workspace"]>;
}) {
  const [personal, setPersonal] = useState(false);

  if (personal) {
    return <Employee onLeave={() => setPersonal(false)} />;
  }

  return (
    <MemberArea
      workspace={workspace}
      onLeave={state.logout}
      onOpenPersonal={() => setPersonal(true)}
    />
  );
}

export { useWorkspace };
