"use client";

import { useState } from "react";

import { CommanderArea, CommanderBar } from "@/components/Complex";
import { CrewLoading } from "@/components/Crew";
import { Employee } from "@/components/Employee";
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
  if (workspace === undefined || state.commander === undefined) {
    return <CrewLoading label="רגע, מכינים הכול…" />;
  }

  // The מכלול commander between משמרות (D43): the combined board. Once they
  // enter one, the team session below takes over. A manager's own session
  // in this browser still wins, as it did before the מכלול existed.
  const ownTeam = Boolean(workspace && !workspace.commander);
  if (state.commander && !ownTeam && !state.inside) {
    return (
      <CommanderArea
        commander={state.commander}
        busy={state.busy}
        onEnter={state.enterTeam}
        onLogout={state.commanderLogout}
      />
    );
  }

  if (workspace === null) {
    return (
      <Login
        busy={state.busy}
        error={state.error}
        onLogin={state.login}
        onEmployeeLogin={state.employeeLogin}
        onCommanderLogin={state.commanderLogin}
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

/** The manager completes manual setup once, then works from the board. */
function BossSurface({
  state,
  workspace,
}: {
  state: ReturnType<typeof useWorkspace>;
  workspace: NonNullable<ReturnType<typeof useWorkspace>["workspace"]>;
}) {
  const [editingSetup, setEditingSetup] = useState(false);
  const taught = Boolean(workspace.profile);
  // The commander inside a workplace (D43): the same screens, under a strip
  // that says so and leads back. Signing out signs the commander out.
  const commanding = Boolean(workspace.commander);
  const bar = commanding ? (
    <CommanderBar
      complexName={workspace.complex?.name ?? ""}
      teamName={workspace.name}
      busy={state.busy}
      onBack={() => void state.leaveTeam()}
    />
  ) : null;

  if (!taught || editingSetup) {
    return (
      <>
        {bar}
        <ManualSetup
          workspace={workspace}
          onCancel={taught ? () => setEditingSetup(false) : undefined}
          onDone={async () => {
            setEditingSetup(false);
            await state.refresh();
          }}
        />
      </>
    );
  }

  return (
    <>
      {bar}
      <Management
        workspace={workspace}
        busy={state.busy}
        onLogout={commanding ? state.commanderLogout : state.logout}
        onRotateLink={state.rotateLink}
        onOpenManualSetup={async () => {
          // The profile and its revision were read at sign-in; the board,
          // the chat and the roster have saved over it since. Setup reads its
          // form from them once, on mount, and names the revision on save.
          await state.refresh();
          setEditingSetup(true);
        }}
      />
    </>
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
