"use client";

// TEMPORARY preview harness — deleted after the screenshot.
import { useState } from "react";

import { Calendar } from "@/components/Management/Calendar";
import type { Assignment, Schedule } from "@/types";
import "@/styles/management.css";
import "@/styles/tokens.css";

const ROSTER = ["דנה", "יוסי", "רון", "מיכל", "אבי", "שירה", "עומר"];
const SHIFTS = ["בוקר", "צהריים", "כונן לילה"];
const DATES = [
  "2026-08-17",
  "2026-08-18",
  "2026-08-19",
  "2026-08-20",
  "2026-08-21",
  "2026-08-22",
];

const slots = DATES.flatMap((date) =>
  SHIFTS.map((shift) => ({
    id: `${shift}-${date}`,
    shift_name: shift,
    slot_date: date,
    start_time: shift === "בוקר" ? "07:00" : shift === "צהריים" ? "15:00" : "23:00",
    end_time: shift === "בוקר" ? "15:00" : shift === "צהריים" ? "23:00" : "07:00",
    headcount: shift === "כונן לילה" ? 1 : 2,
    is_on_call: shift === "כונן לילה",
  })),
);

const PLACED: Array<[string, string, string, string]> = [
  ["דנה", "בוקר", "2026-08-17", "agent"],
  ["יוסי", "בוקר", "2026-08-17", "agent"],
  ["רון", "צהריים", "2026-08-17", "agent"],
  ["מיכל", "כונן לילה", "2026-08-17", "manager"],
  ["דנה", "בוקר", "2026-08-18", "agent"],
  ["שירה", "צהריים", "2026-08-18", "manager"],
  ["עומר", "צהריים", "2026-08-18", "agent"],
  ["רון", "בוקר", "2026-08-19", "agent"],
  ["אבי", "בוקר", "2026-08-19", "agent"],
  ["דנה", "צהריים", "2026-08-19", "agent"],
  ["יוסי", "כונן לילה", "2026-08-19", "agent"],
  ["מיכל", "בוקר", "2026-08-20", "manager"],
  ["שירה", "צהריים", "2026-08-20", "agent"],
  ["דנה", "בוקר", "2026-08-21", "agent"],
  ["עומר", "בוקר", "2026-08-21", "agent"],
  ["רון", "כונן לילה", "2026-08-21", "manager"],
  ["אבי", "בוקר", "2026-08-22", "agent"],
];

const SCHEDULE: Schedule = {
  id: "preview",
  starts_on: DATES[0],
  ends_on: DATES[DATES.length - 1],
  status: "draft",
  slots,
  assignments: PLACED.map(([employee, shift, date, source], i) => ({
    id: `a${i}`,
    employee,
    shift,
    date,
    reason: `${employee} מוסמך/ת למשמרת ${shift}`,
    slot_id: `${shift}-${date}`,
    source: source as Assignment["source"],
  })),
  warnings: [
    {
      code: "unfilled",
      severity: "warning",
      message: "משמרת צהריים ב-21.8 ללא איוש",
      employee: "",
      date: "2026-08-21",
      shift: "צהריים",
      details: {},
    },
    {
      code: "consecutive",
      severity: "warning",
      message: "דנה משובצת 5 ימים ברצף",
      employee: "דנה",
      date: "2026-08-21",
      shift: "בוקר",
      details: {},
    },
  ],
  notes: [],
  summary: "",
};

const CONSTRAINTS = [
  {
    id: "c1",
    employee: "אבי",
    constraint_date: "2026-08-22",
    shift_name: "בוקר",
    available: false,
    reason: "לימודים",
    source: "employee_reported",
  },
] as never;

export default function Preview() {
  const [dark, setDark] = useState(false);
  // The tokens are scoped to :root, so the toggle has to move the attribute
  // on <html> exactly as the real useTheme hook does.
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  }
  return (
    <div className="management">
      <main className="management-body">
        <div className="management-main">
          <div className="management-toolbar">
            <div className="period">
              <span className="period-range">17.8 – 22.8</span>
              <span className="period-status is-draft">טיוטה</span>
            </div>
            <div className="toolbar-actions">
              <button
                type="button"
                className="ghost-button"
                onClick={() => setDark((d) => !d)}
              >
                {dark ? "בהיר" : "כהה"}
              </button>
              <button type="button" className="ghost-button">
                סידור ריק
              </button>
              <button type="button" className="primary-button">
                בניית סידור לשבוע
              </button>
            </div>
          </div>
          <Calendar
            schedule={SCHEDULE}
            constraints={CONSTRAINTS}
            employees={ROSTER}
            dark={dark}
            onDrop={() => {}}
            onAssign={() => {}}
            onUnassign={() => {}}
          />
        </div>
      </main>
    </div>
  );
}
