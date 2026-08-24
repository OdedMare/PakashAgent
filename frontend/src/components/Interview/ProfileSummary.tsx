"use client";

import { CheckCircle2 } from "lucide-react";

import type { WorkplaceProfile } from "@/types";

/** What the interview produced, once the boss confirmed the summary.
 *
 *  The counts are the useful part — they are what the scheduler and the
 *  audit will run on. The full profile stays available as JSON rather than
 *  being mirrored field-by-field here, because `bl/interview.py` owns that
 *  shape and a second copy of it would drift on the first schema change. */
export function ProfileSummary({ profile }: { profile: WorkplaceProfile }) {
  const workplace = profile.workplace ?? {};
  const summary =
    (typeof profile.summary === "string" && profile.summary) ||
    workplace.summary ||
    workplace.mission ||
    "";

  return (
    <div className="done">
      <div className="done-head">
        <CheckCircle2 size={19} />
        <span>הראיון הושלם</span>
      </div>
      <p>
        {workplace.name ? `${workplace.name}. ` : ""}
        {summary}
      </p>

      <dl className="profile-grid">
        <Stat label="אנשי צוות" value={count(profile.employees)} />
        <Stat label="סוגי משמרות" value={count(profile.shifts)} />
        <Stat label="כללים" value={count(profile.rules)} />
      </dl>

      <details className="profile-json">
        <summary>הפרופיל המלא</summary>
        <pre>{JSON.stringify(profile, null, 2)}</pre>
      </details>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="profile-card">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function count(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}
