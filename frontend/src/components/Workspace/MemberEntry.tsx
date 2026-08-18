"use client";

import { AlertCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { openMemberLink } from "@/services/api";

import { Workspace } from "./index";

/** Redeems a share link, then hands over to the ordinary workspace render.
 *
 *  Two things happen on arrival, in this order: the token is exchanged for an
 *  HttpOnly cookie, and the URL is rewritten to `/` so the token stops
 *  travelling with every subsequent navigation. `replaceState` rather than a
 *  router push, so the token-bearing URL is not left behind in the back
 *  stack. */
export function MemberEntry({ token }: { token: string }) {
  const [failed, setFailed] = useState(false);
  const [done, setDone] = useState(false);
  // React 18 mounts effects twice in development. Redeeming twice is
  // harmless — the token is not consumed — but the guard keeps the network
  // trace honest about what actually happened.
  const redeemed = useRef(false);

  useEffect(() => {
    if (redeemed.current) return;
    redeemed.current = true;
    openMemberLink(token)
      .then(() => {
        window.history.replaceState(null, "", "/");
        setDone(true);
      })
      .catch(() => setFailed(true));
  }, [token]);

  if (failed) {
    return (
      <div className="workspace-gate">
        <div className="gate-card">
          <div className="gate-error" role="alert">
            <AlertCircle size={15} />
            <span>הקישור אינו תקף או שפג תוקפו.</span>
          </div>
          <p className="gate-lede">
            בקשו מהמנהל קישור מעודכן — ייתכן שנוצר קישור חדש שביטל את הישן.
          </p>
        </div>
      </div>
    );
  }

  if (!done) {
    return <div className="workspace-gate" aria-busy="true" />;
  }

  return <Workspace />;
}
