"use client";

import { LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { getReplacementOptions } from "@/services/api";
import type { DepartureCover } from "@/services/api";
import type { ReplacementOptions } from "@/types";

import { ReplacementSlotCard } from "./ReplacementPanel";

// The replacement search's own limit (`_MAX_ABSENCE_DAYS` on the server).
const SEARCH_DAYS = 120;

/** Who could take over the shifts a departure vacates.
 *
 *  The replacement tab's search, asked about every day from the departure
 *  date on: candidates already pass the placement checks and come fairest
 *  first, with the fair pick preselected. Nothing here writes — the picks
 *  go back through `onChange`, and the departure places them after it
 *  vacates the shifts. One search plans one stored period, so shifts in
 *  later periods are only counted, and stay vacant. */
export function DepartureCovers({ employee, date, onChange }: {
  employee: string;
  date: string;
  /** Stable, like a state setter: it is an effect dependency. */
  onChange: (covers: { date: string; rows: DepartureCover[] }) => void;
}) {
  // Keyed by the person and date searched, so an answer for another date
  // never shows and never feeds the picks.
  const [found, setFound] = useState<{ key: string; options?: ReplacementOptions; error?: string } | null>(null);
  const [chosen, setChosen] = useState<Record<string, string>>({});
  const key = `${employee}:${date}`;
  const options = found?.key === key ? found.options ?? null : null;
  const error = found?.key === key ? found.error ?? "" : "";

  useEffect(() => {
    if (!employee || !date) return;
    let live = true;
    const timer = setTimeout(() => {
      getReplacementOptions(employee, date, addDays(date, SEARCH_DAYS - 1)).then((next) => {
        if (!live) return;
        setFound({ key, options: next });
        setChosen(Object.fromEntries(next.slots.map((slot) => [slotKey(slot), slot.pick])));
      }).catch((reason) => {
        if (live) setFound({ key, error: reason instanceof Error ? reason.message : "לא ניתן לחפש מחליפים" });
      });
    }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [employee, date, key]);

  useEffect(() => {
    onChange({ date, rows: options ? options.slots
      .filter((slot) => chosen[slotKey(slot)])
      .map((slot) => ({
        schedule_id: options.schedule_id,
        shift_name: slot.shift,
        slot_date: slot.date,
        employee: chosen[slotKey(slot)],
      })) : [] });
  }, [date, options, chosen, onChange]);

  if (error) return <p className="replacement-error" role="alert">{error}</p>;
  if (options?.error) return <p className="replacement-error" role="alert">{options.error}</p>;
  if (!options) {
    return <p className="replacement-status" role="status"><LoaderCircle size={15} /> מחפש מי יכול/ה להחליף…</p>;
  }
  if (!options.slots.length) return null;
  const later = options.elsewhere?.length ?? 0;
  return (
    <div className="departure-covers">
      <p className="replacement-status">
        מי יחליף/תחליף את {employee}? המועמדים מסודרים כך שהעומס יתחלק הכי שווה.
        אפשר לבטל בחירה בלחיצה נוספת — המשמרת תישאר פנויה.
      </p>
      {options.slots.map((slot) => (
        <ReplacementSlotCard
          key={slotKey(slot)}
          slot={slot}
          chosen={chosen[slotKey(slot)] ?? ""}
          disabled={false}
          onChoose={(name) => setChosen((previous) => ({
            ...previous,
            [slotKey(slot)]: previous[slotKey(slot)] === name ? "" : name,
          }))}
        />
      ))}
      {later ? (
        <p className="replacement-status">
          {later === 1 ? "משמרת אחת נוספת" : `${later} משמרות נוספות`} בתקופות מאוחרות יותר
          {" "}יישארו פנויות — אפשר למלא אותן מהלוח או מטאב ההחלפות.
        </p>
      ) : null}
    </div>
  );
}

function slotKey(slot: { date: string; shift: string }) {
  return `${slot.date}:${slot.shift}`;
}

function addDays(iso: string, days: number): string {
  const day = new Date(`${iso}T00:00:00Z`);
  day.setUTCDate(day.getUTCDate() + days);
  return day.toISOString().slice(0, 10);
}
