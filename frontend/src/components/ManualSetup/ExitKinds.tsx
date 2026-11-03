"use client";

/** "איך יוצאים אצלכם?" — the rotation section's first question.
 *
 *  A unit picks the kinds of exits it actually has, and only those open
 *  their own questions below; a unit with no rotation answers once and is
 *  done. Each kind is a way of reading one or more stored exit patterns:
 *
 *  - none, daily and personal (1 ל-N) are one pattern each, set per soldier;
 *  - weekend groups are the lettered cycles, chosen by how many groups take
 *    turns (2 = סבב, 3 = תלתון, 4 = רבעון, 5 = חמישון);
 *  - every weekend home is חמשושים (from Thursday) or שושים (from Friday);
 *  - days on base / days home are the day cycles (11/3, 12/2…);
 *  - reservists are a service type with days a week, set per soldier.
 *
 *  What is chosen is saved as `enabled_exit_patterns`; a pattern somebody
 *  is on cannot be switched off here, so nobody is left on a hidden one. */

export type Kind = "none" | "daily" | "weekends" | "every_weekend" | "days" | "personal" | "reserve";

export const GROUP_CYCLES = [
  { pattern: "round", groups: 2, label: "2 קבוצות", detail: "סבב — כל קבוצה סוגרת פעם בשבועיים" },
  { pattern: "triplet", groups: 3, label: "3 קבוצות", detail: "תלתון — שבת אחת מכל שלוש" },
  { pattern: "quad", groups: 4, label: "4 קבוצות", detail: "רבעון — שבת אחת מכל ארבע" },
  { pattern: "quint", groups: 5, label: "5 קבוצות", detail: "חמישון — שבת אחת מכל חמש (1ל5)" },
] as const;

const WEEKLY = [
  { pattern: "hamshushim", label: "מחמישי", detail: "חמשושים — בבית מחמישי עד ראשון" },
  { pattern: "shushim", label: "משישי", detail: "שושים — בבית משישי עד ראשון" },
] as const;

const KINDS: { kind: Kind; title: string; detail: string; patterns: string[] }[] = [
  { kind: "none", title: "בלי יציאות", detail: "קבע, אזרחים, או כל מי שהסידור לא צריך לחשב לו יציאות.", patterns: ["none"] },
  { kind: "daily", title: "הולכים הביתה כל יום", detail: "מגיעים בימים ובשעות קבועים וחוזרים הביתה בערב.", patterns: ["daily"] },
  { kind: "weekends", title: "קבוצות שסוגרות שבתות בתורות", detail: "סבב, תלתון, רבעון או חמישון — קבוצה אחת בבסיס בכל סופ״ש.", patterns: GROUP_CYCLES.map((item) => item.pattern) },
  { kind: "days", title: "ימים בבסיס / ימים בבית", detail: "11/3, 12/2, שבוע־שבוע או כל מחזור ימים אחר.", patterns: [] },
  { kind: "every_weekend", title: "כל סופ״ש בבית", detail: "חמשושים או שושים — יוצאים כל שבוע.", patterns: WEEKLY.map((item) => item.pattern) },
  { kind: "personal", title: "סגירה אישית 1 ל־N", detail: "חייל/ת אחד/ת שסוגר/ת שבת אחת מכל כמה, בלי קבוצה. למשל מפקד 1ל5.", patterns: ["personal"] },
  { kind: "reserve", title: "מילואים — כמה ימים בשבוע", detail: "פעיל: המילואימניקים מגיעים ונכללים בשיבוץ. כבוי: הסידור מתעלם מהם.", patterns: [] },
];

export function ExitKinds({ enabled, used, counts, dayCyclesOn, reserveOn, reserveBusy, onEnabled, onDayCycles, onReserve }: {
  enabled: Set<string>;
  /** Patterns somebody on the roster is on: locked on. */
  used: Set<string>;
  /** People per pattern ("cycle:*" counted under "days", reservists under "reserve"). */
  counts: Record<string, number>;
  dayCyclesOn: boolean;
  reserveOn: boolean;
  reserveBusy: boolean;
  onEnabled: (patterns: Set<string>) => void;
  onDayCycles: (on: boolean) => void;
  onReserve: (on: boolean) => void;
}) {
  const isOn = (kind: Kind, patterns: string[]) => kind === "days" ? dayCyclesOn : kind === "reserve" ? reserveOn
    : patterns.some((pattern) => enabled.has(pattern));
  const lockedKind = (kind: Kind, patterns: string[]) => kind === "days" ? (counts.days ?? 0) > 0
    : kind === "reserve" ? false : patterns.some((pattern) => used.has(pattern));
  const people = (kind: Kind, patterns: string[]) => kind === "days" || kind === "reserve" ? counts[kind] ?? 0
    : patterns.reduce((sum, pattern) => sum + (counts[pattern] ?? 0), 0);

  const toggle = (kind: Kind, patterns: string[], on: boolean) => {
    if (kind === "days") return onDayCycles(on);
    if (kind === "reserve") return onReserve(on);
    const next = new Set(enabled);
    // Turning a family on picks its commonest member; the sub-choices below refine it.
    const first = kind === "weekends" ? ["round"] : kind === "every_weekend" ? ["hamshushim"] : patterns;
    if (on) first.forEach((pattern) => next.add(pattern));
    else patterns.filter((pattern) => !used.has(pattern)).forEach((pattern) => next.delete(pattern));
    onEnabled(next);
  };
  const setOne = (pattern: string, on: boolean) => {
    const next = new Set(enabled);
    if (on) next.add(pattern); else if (!used.has(pattern)) next.delete(pattern);
    onEnabled(next);
  };

  return (
    <div className="exit-kinds">
      <p className="exit-kinds-question"><strong>איך יוצאים אצלכם?</strong> סמנו כל מה שקיים ביחידה — אפשר כמה. רק מה שסימנתם ייפתח למטה ויופיע בבחירה של כל חייל/ת.</p>
      <div className="exit-kind-grid">
        {KINDS.map(({ kind, title, detail, patterns }) => {
          const on = isOn(kind, patterns);
          const locked = on && lockedKind(kind, patterns);
          const checking = kind === "reserve" && reserveBusy;
          const count = people(kind, patterns);
          return (
            <label key={kind} className={`exit-kind${on ? " is-selected" : ""}`} title={checking ? "בודק שיבוצים עתידיים…" : locked ? "יש אנשי צוות במבנה הזה" : undefined}>
              <input type="checkbox" checked={on} disabled={locked || checking} onChange={(event) => toggle(kind, patterns, event.target.checked)} />
              <strong>{title}</strong>
              <span>{detail}</span>
              {count ? <em>{count === 1 ? "איש צוות אחד" : `${count} אנשי צוות`}</em> : null}
            </label>
          );
        })}
      </div>
      {isOn("weekends", KINDS[2].patterns) ? (
        <SubChoice legend="כמה קבוצות מתחלפות?" items={GROUP_CYCLES} enabled={enabled} used={used} counts={counts} onChange={setOne} />
      ) : null}
      {isOn("every_weekend", KINDS[4].patterns) ? (
        <SubChoice legend="מתי יוצאים?" items={WEEKLY} enabled={enabled} used={used} counts={counts} onChange={setOne} />
      ) : null}
    </div>
  );
}

function SubChoice({ legend, items, enabled, used, counts, onChange }: {
  legend: string;
  items: readonly { pattern: string; label: string; detail: string }[];
  enabled: Set<string>; used: Set<string>; counts: Record<string, number>;
  onChange: (pattern: string, on: boolean) => void;
}) {
  return (
    <fieldset className="exit-subchoice">
      <legend>{legend}</legend>
      <div className="closure-shapes">
        {items.map(({ pattern, label, detail }) => (
          <label key={pattern} className={`closure-shape${enabled.has(pattern) ? " is-selected" : ""}`}>
            <input type="checkbox" checked={enabled.has(pattern)} disabled={used.has(pattern)} onChange={(event) => onChange(pattern, event.target.checked)} />
            <strong>{label}</strong>
            <span>{detail}{counts[pattern] ? ` · ${counts[pattern]} אנשי צוות` : ""}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
