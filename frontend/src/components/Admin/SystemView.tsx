"use client";

import { Activity, Cpu, Database, HardDrive, Settings2 } from "lucide-react";

import { SystemSettings } from "@/components/Settings";

import { formatBytes } from "./format";
import type { AdminState } from "./useAdmin";

const MODE_LABEL: Record<string, string> = { day: "יום בכל קריאה", week: "שבוע בכל קריאה" };

/** The server as a whole: is it healthy, what model is it running, and the
 *  settings every workspace shares. The settings used to be reachable only
 *  from inside some team's management area, with a second password; here
 *  they sit with the operator, whose session is the credential. */
export function SystemView({ state }: { state: AdminState }) {
  const overview = state.overview;
  const totals = overview?.totals ?? {};
  const model = overview?.model ?? {};
  const roles = [
    ["מהיר", model.llm_model_fast],
    ["רגיל", model.llm_model_default],
    ["מתקדם", model.llm_model_advanced],
  ].filter(([, value]) => value);

  return (
    <>
      <section className="adm-health" aria-label="מצב המערכת">
        <div className={`adm-health-card ${overview?.database === "error" ? "is-bad" : "is-good"}`}>
          <Database size={18} aria-hidden="true" />
          <span>
            <small>מסד נתונים</small>
            <strong>{overview ? (overview.database === "ok" ? "תקין" : "לא זמין") : "—"}</strong>
          </span>
        </div>
        <div className="adm-health-card">
          <Cpu size={18} aria-hidden="true" />
          <span>
            <small>מודל ראשי</small>
            <strong dir="ltr">{model.llm_model || "—"}</strong>
            {roles.length ? (
              <em>{roles.map(([label, value]) => `${label}: ${value}`).join(" · ")}</em>
            ) : null}
          </span>
        </div>
        <div className="adm-health-card">
          <Activity size={18} aria-hidden="true" />
          <span>
            <small>בניית סידור</small>
            <strong>{MODE_LABEL[model.schedule_generation_mode] ?? (model.schedule_generation_mode || "—")}</strong>
          </span>
        </div>
        <div className="adm-health-card">
          <HardDrive size={18} aria-hidden="true" />
          <span>
            <small>נפח הנתונים</small>
            <strong dir="ltr">{formatBytes(totals.database_bytes)}</strong>
            <em>
              {totals.assignments ?? 0} שיבוצים · {totals.changes ?? 0} שינויים ביומן
            </em>
          </span>
        </div>
      </section>

      <section className="adm-panel adm-settings" aria-labelledby="adm-settings-title">
        <div className="adm-panel-head">
          <div>
            <h2 id="adm-settings-title">
              <Settings2 size={18} aria-hidden="true" /> הגדרות המערכת
            </h2>
            <p>
              משותפות לכל הצוותים: חיבור המודל, מפתחות, מסד הנתונים ואופן בניית הסידור. שינוי כאן
              משפיע על כולם מיד.
            </p>
          </div>
        </div>
        <SystemSettings />
      </section>
    </>
  );
}
