"use client";

import { ArrowRight, Network } from "lucide-react";

/** A floating pill over the management area while the מכלול commander is
 *  inside a משמרת (D43). Everything below it is the workplace's own control
 *  room, with a manager's powers; this only says whose hands it is in and
 *  leads back to the combined board. */
export function CommanderBar({
  complexName,
  teamName,
  busy,
  onBack,
}: {
  complexName: string;
  teamName: string;
  busy: boolean;
  onBack: () => void;
}) {
  return (
    <div className="cmd-bar" role="region" aria-label="מצב מפקד מכלול">
      <Network size={15} aria-hidden="true" />
      <span>
        <strong>מפקד מכלול {complexName}</strong> · בתוך <strong>{teamName}</strong>
        <span className="cmd-bar-note"> · כל שינוי נשלח למפקד המשמרת</span>
      </span>
      <button type="button" className="ghost-button" onClick={onBack} disabled={busy}>
        <ArrowRight size={14} /> חזרה ללוח המכלול
      </button>
    </div>
  );
}
