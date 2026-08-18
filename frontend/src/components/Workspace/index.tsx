"use client";

import { useState } from "react";

import { Interview } from "@/components/Interview";
import { Management } from "@/components/Management";

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
    return <MemberArea workspace={workspace} onLeave={state.logout} />;
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
  const [reinterview, setReinterview] = useState(false);
  const taught = Boolean(workspace.profile);

  if (taught && !reinterview) {
    return (
      <Management
        workspace={workspace}
        busy={state.busy}
        onLogout={state.logout}
        onRotateLink={state.rotateLink}
        onOpenInterview={() => setReinterview(true)}
      />
    );
  }

  return (
    <Interview
      workspace={workspace}
      busy={state.busy}
      onLogout={state.logout}
      onRotateLink={state.rotateLink}
      onDone={taught ? () => setReinterview(false) : undefined}
    />
  );
}

export { useWorkspace };
