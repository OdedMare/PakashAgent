"use client";

import {
  AlertCircle,
  Check,
  Copy,
  KeyRound,
  Link2,
  RefreshCw,
  Save,
  UserX,
  WandSparkles,
} from "lucide-react";
import { FormEvent, useState } from "react";

import {
  adminReleaseIdentity,
  adminResetPassword,
  adminRotateLink,
  adminUpdateTeam,
} from "@/services/api";
import type { AdminTeamDetail } from "@/types";

import { formatRelative, formatShort, generatePassword } from "./format";

type Changed = (next?: AdminTeamDetail) => Promise<void>;

/** Run one write, reporting its error in place rather than in a toast far
 *  from the button that caused it. */
function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const run = async (action: () => Promise<void>, success?: string) => {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      await action();
      if (success) setDone(success);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "שגיאה לא ידועה");
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, done, run };
}

function Feedback({ error, done }: { error: string | null; done: string | null }) {
  if (error) {
    return (
      <div className="adm-alert is-danger" role="alert">
        <AlertCircle size={15} /> <span>{error}</span>
      </div>
    );
  }
  if (done) {
    return (
      <div className="adm-alert is-success" role="status">
        <Check size={15} /> <span>{done}</span>
      </div>
    );
  }
  return null;
}

export function SettingsSection({ team, onChanged }: { team: AdminTeamDetail; onChanged: Changed }) {
  const [name, setName] = useState(team.name);
  const [seats, setSeats] = useState(team.max_employees?.toString() ?? "");
  const [notes, setNotes] = useState(team.notes);
  const action = useAction();

  const seatValue = seats.trim() === "" ? null : Number.parseInt(seats, 10);
  const seatsValid = seatValue === null || (Number.isInteger(seatValue) && seatValue >= 1 && seatValue <= 5000);
  const dirty = name.trim() !== team.name || seatValue !== team.max_employees || notes.trim() !== team.notes;

  const save = (event: FormEvent) => {
    event.preventDefault();
    if (!dirty || !seatsValid || !name.trim()) return;
    void action.run(async () => {
      await onChanged(await adminUpdateTeam(team.id, {
        name: name.trim(),
        max_employees: seatValue,
        notes: notes.trim(),
      }));
    }, "נשמר");
  };

  return (
    <form className="adm-section" onSubmit={save}>
      <h3>פרטי הצוות ומכסה</h3>
      <label className="adm-field">
        <span>שם הצוות</span>
        <input value={name} maxLength={80} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="adm-field">
        <span>מכסת עובדים</span>
        <input
          type="number"
          inputMode="numeric"
          min={1}
          max={5000}
          placeholder="ללא הגבלה"
          value={seats}
          aria-invalid={!seatsValid}
          onChange={(event) => setSeats(event.target.value)}
        />
        <small>
          כרגע {team.employees} עובדים פעילים. השאירו ריק לביטול ההגבלה. הורדה מתחת למספר הנוכחי לא
          מוחקת אף אחד — רק מונעת הוספה.
        </small>
      </label>
      <label className="adm-field">
        <span>הערה פנימית</span>
        <textarea rows={2} maxLength={500} value={notes} onChange={(event) => setNotes(event.target.value)} />
      </label>
      <Feedback error={action.error} done={action.done} />
      <div className="adm-section-actions">
        <button type="submit" className="adm-gold-button" disabled={!dirty || !seatsValid || action.busy}>
          <Save size={15} /> {action.busy ? "שומר…" : "שמירה"}
        </button>
      </div>
    </form>
  );
}

export function AccessSection({ team, onChanged }: { team: AdminTeamDetail; onChanged: Changed }) {
  const [password, setPassword] = useState("");
  const [copied, setCopied] = useState(false);
  const reset = useAction();
  const link = useAction();
  const shareUrl = typeof window === "undefined" ? "" : `${window.location.origin}/team/${team.member_token}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="adm-section">
      <h3>גישה</h3>
      <form
        className="adm-field"
        onSubmit={(event) => {
          event.preventDefault();
          if (password.length < 6) return;
          void reset.run(async () => {
            await adminResetPassword(team.id, password);
            await onChanged();
          }, `הסיסמה החדשה: ${password}`);
        }}
      >
        <span><KeyRound size={14} aria-hidden="true" /> איפוס סיסמת מנהל</span>
        <span className="adm-input-row">
          <input
            dir="ltr"
            value={password}
            minLength={6}
            placeholder="סיסמה חדשה"
            autoComplete="new-password"
            data-1p-ignore="true"
            data-lpignore="true"
            onChange={(event) => setPassword(event.target.value)}
          />
          <button type="button" className="adm-quiet-button" onClick={() => setPassword(generatePassword())}>
            <WandSparkles size={14} />
          </button>
          <button type="submit" className="adm-quiet-button" disabled={password.length < 6 || reset.busy}>
            קביעה
          </button>
        </span>
        <small>למנהל ששכח את הסיסמה. הסיסמה הקודמת מפסיקה לעבוד מיד.</small>
      </form>
      <Feedback error={reset.error} done={reset.done} />

      <div className="adm-field">
        <span><Link2 size={14} aria-hidden="true" /> קישור הצוות לעובדים</span>
        <span className="adm-input-row">
          <input dir="ltr" readOnly value={shareUrl} onFocus={(event) => event.target.select()} />
          <button type="button" className="adm-quiet-button" onClick={() => void copy()}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button
            type="button"
            className="adm-quiet-button"
            disabled={link.busy}
            onClick={() => void link.run(async () => onChanged(await adminRotateLink(team.id)), "נוצר קישור חדש; הקודם בוטל")}
          >
            <RefreshCw size={14} /> חידוש
          </button>
        </span>
        <small>חידוש מבטל את הקישור הקודם לכל מי שמחזיק בו.</small>
      </div>
      <Feedback error={link.error} done={link.done} />
    </section>
  );
}

export function PeopleSection({ team, onChanged }: { team: AdminTeamDetail; onChanged: Changed }) {
  const release = useAction();
  const today = new Date().toISOString().slice(0, 10);
  return (
    <section className="adm-section">
      <h3>עובדים ({team.employees}{team.roster_total > team.employees ? ` · ${team.roster_total - team.employees} סיימו` : ""})</h3>
      {team.profile_employees.length === 0 ? (
        <p className="adm-muted">הצוות עוד לא הגדיר עובדים.</p>
      ) : (
        <ul className="adm-people">
          {team.profile_employees.map((person) => {
            const left = Boolean(person.inactive_from && person.inactive_from <= today);
            const claimed = team.identities_list.find((row) => row.employee === person.name);
            return (
              <li key={person.name} className={left ? "is-left" : undefined}>
                <span>
                  <strong>{person.name}</strong>
                  <small>{[person.role, left ? "סיים/ה" : ""].filter(Boolean).join(" · ") || "—"}</small>
                </span>
                {claimed ? (
                  <button
                    type="button"
                    className="adm-chip-button"
                    title={`כניסה אחרונה ${formatRelative(claimed.last_seen_at)}`}
                    disabled={release.busy}
                    onClick={() => void release.run(async () => onChanged(await adminReleaseIdentity(team.id, person.name)))}
                  >
                    <UserX size={13} /> שחרור כניסה
                  </button>
                ) : (
                  <span className="adm-chip-muted">ללא כניסה אישית</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
      <Feedback error={release.error} done={null} />
    </section>
  );
}

const STATUS_LABEL: Record<string, string> = { draft: "טיוטה", published: "פורסם" };

export function ActivitySection({ team }: { team: AdminTeamDetail }) {
  return (
    <section className="adm-section">
      <h3>סידורים ופעילות</h3>
      {team.periods_list.length === 0 ? (
        <p className="adm-muted">עדיין לא נבנה סידור.</p>
      ) : (
        <ul className="adm-periods">
          {team.periods_list.map((period) => (
            <li key={period.id}>
              <span dir="ltr">{formatShort(period.starts_on)} – {formatShort(period.ends_on)}</span>
              <span className={`adm-pill ${period.status === "published" ? "is-on" : "is-setup"}`}>
                {STATUS_LABEL[period.status] ?? period.status}
              </span>
              <small>{period.assignments} שיבוצים</small>
            </li>
          ))}
        </ul>
      )}
      {team.recent_changes.length ? (
        <>
          <h4>שינויים אחרונים</h4>
          <ul className="adm-changes">
            {team.recent_changes.map((change, index) => (
              <li key={`${change.created_at}-${index}`}>
                <span>
                  {change.employee || "—"}
                  {change.shift_name ? ` · ${change.shift_name}` : ""}
                  {change.slot_date ? ` · ${formatShort(change.slot_date)}` : ""}
                </span>
                <small>{change.reason || change.action} · {formatRelative(change.created_at)}</small>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}
