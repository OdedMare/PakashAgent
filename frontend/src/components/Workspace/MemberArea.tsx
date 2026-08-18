"use client";

import { CalendarClock, LogOut, Moon, Sun, Users } from "lucide-react";

import { useTheme } from "@/components/Interview/useTheme";
import type { TeamView } from "@/types";

/** What a team member sees.
 *
 *  Read-only, and not by omission — D5 makes the boss the sole actor, so this
 *  surface deliberately has no controls to edit, accept, decline, or submit
 *  availability. Adding one here would reverse a settled decision, not extend
 *  a screen.
 *
 *  The schedule grid itself waits on `bl/scheduler.py` and the `schedules`
 *  table, neither of which exists yet (docs/BUILD_ORDER.md steps 5–7). Rather
 *  than render a plausible-looking empty grid whose shape is a guess at data
 *  that has never been produced, this says plainly that nothing is published
 *  yet — and slots the grid in unchanged when it is. */
export function MemberArea({
  workspace,
  onLeave,
}: {
  workspace: TeamView;
  onLeave: () => void;
}) {
  const { theme, toggle } = useTheme();
  const shifts = readShiftNames(workspace.profile);

  return (
    <div className="interview">
      <header className="interview-header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Users size={17} />
          </span>
          <span>
            {workspace.name}
            <span className="brand-sub"> · תצוגת עובד</span>
          </span>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="icon-button"
            onClick={toggle}
            aria-label={theme === "dark" ? "מצב בהיר" : "מצב כהה"}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <button
            type="button"
            className="icon-button"
            onClick={onLeave}
            aria-label="יציאה"
            title="יציאה"
          >
            <LogOut size={17} />
          </button>
        </div>
      </header>

      <main id="interview">
        <div className="center">
          <span className="brand-mark" aria-hidden="true">
            <CalendarClock size={17} />
          </span>
          <h1>הסידור עוד לא פורסם</h1>
          <p>
            כאן יופיע הסידור של {workspace.name} ברגע שהמנהל יפרסם אותו. הדף
            הזה לצפייה בלבד — שינויים נעשים מול המנהל.
          </p>
          {shifts.length > 0 ? (
            <p className="member-shifts">
              המשמרות בצוות: {shifts.join(" · ")}
            </p>
          ) : null}
        </div>
      </main>
    </div>
  );
}

/** Shift names as the interview recorded them.
 *
 *  Read defensively: the profile is model-produced JSON whose exact shape the
 *  interview owns, so a missing or differently-keyed field must degrade to
 *  showing nothing rather than throwing. Never hardcode shift names — they
 *  are per-workplace data (D9). */
function readShiftNames(profile: TeamView["profile"]): string[] {
  const shifts = profile?.shifts;
  if (!Array.isArray(shifts)) return [];
  return shifts
    .map((shift) =>
      typeof shift === "string"
        ? shift
        : ((shift as { name?: unknown })?.name ?? ""),
    )
    .filter((name): name is string => typeof name === "string" && name !== "");
}
