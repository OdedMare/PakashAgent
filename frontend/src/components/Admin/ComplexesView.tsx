"use client";

import { AlertCircle, Network, Pencil, Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { adminComplexes } from "@/services/api";
import type { AdminComplex } from "@/types";

import { ComplexDialog } from "./ComplexDialog";
import { formatDate } from "./format";
import type { AdminState } from "./useAdmin";

/** Every מכלול on the server (D43): existing workplaces joined under one
 *  commander. Opening one links teams that already exist; nothing inside a
 *  team changes by joining. */
export function ComplexesView({ state }: { state: AdminState }) {
  const [complexes, setComplexes] = useState<AdminComplex[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<AdminComplex | null | "new">(null);

  const reload = useCallback(async () => {
    try {
      setComplexes(await adminComplexes());
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    adminComplexes()
      .then((rows) => !cancelled && setComplexes(rows))
      .catch((reason) => !cancelled && setError(reason instanceof Error ? reason.message : "שגיאה"));
    return () => {
      cancelled = true;
    };
  }, []);

  const changed = async () => {
    await Promise.all([reload(), state.reload()]);
  };

  return (
    <section className="adm-panel" aria-labelledby="adm-complexes-title">
      <div className="adm-panel-head">
        <div>
          <h2 id="adm-complexes-title">מכלולים</h2>
          <p>כמה משמרות תחת מפקד מכלול אחד. לכל משמרת נשאר מפקד משמרת משלה; מפקד המכלול רואה ועורך את כולן.</p>
        </div>
        <button type="button" className="adm-gold-button" onClick={() => setEditing("new")}>
          <Plus size={16} /> פתיחת מכלול חדש
        </button>
      </div>

      {error ? (
        <div className="adm-alert is-danger" role="alert">
          <AlertCircle size={15} /> <span>{error}</span>
        </div>
      ) : null}

      {complexes === null ? (
        <div className="adm-empty" aria-busy="true">טוען מכלולים…</div>
      ) : complexes.length === 0 ? (
        <div className="adm-empty">
          <Network size={22} aria-hidden="true" />
          <strong>עדיין לא נפתח מכלול</strong>
          <span>בחרו משמרות קיימות, קבעו סיסמת מפקד מכלול, והוא נכנס מדף הכניסה.</span>
        </div>
      ) : (
        <ul className="adm-complexes" aria-label="רשימת המכלולים">
          {complexes.map((row) => (
            <li key={row.id} className={row.active ? "" : "is-suspended"}>
              <div className="adm-complex-head">
                <span className="adm-team-name">
                  <strong>{row.name}</strong>
                  <small>{row.notes || `נפתח ${formatDate(row.created_at)}`}</small>
                </span>
                <span className={`adm-pill ${row.active ? "is-on" : "is-off"}`}>
                  {row.active ? "פעיל" : "מושבת"}
                </span>
                <button type="button" className="adm-quiet-button" onClick={() => setEditing(row)}>
                  <Pencil size={14} /> עריכה
                </button>
              </div>
              <div className="adm-complex-chips">
                {row.teams.length === 0 ? (
                  <span className="adm-chip-muted">אין משמרות משויכות</span>
                ) : (
                  row.teams.map((team) => (
                    <span key={team.id} className={`adm-pill ${team.active ? "is-setup" : "is-off"}`}>
                      {team.name}
                    </span>
                  ))
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing !== null ? (
        <ComplexDialog
          complex={editing === "new" ? null : editing}
          teams={state.teams ?? []}
          onClose={() => setEditing(null)}
          onChanged={changed}
        />
      ) : null}
    </section>
  );
}
