"use client";

import { Interview } from "@/components/Interview";

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

  return (
    <Interview
      workspace={workspace}
      busy={state.busy}
      onLogout={state.logout}
      onRotateLink={state.rotateLink}
    />
  );
}

export { useWorkspace };
