"use client";

// TEMPORARY preview harness — deleted after the screenshot.
import { Stats } from "@/components/Management/Stats";
import "@/styles/management.css";

const STATS = {"total_hours": 140.0, "total_shifts": 19, "people_working": 4, "coverage": {"required": 28, "assigned": 19, "unfilled_slots": 8, "percent": 67.9}, "by_shift": [{"shift": "בוקר", "count": 11, "hours": 88.0, "is_on_call": false}, {"shift": "כונן לילה", "count": 3, "hours": 12.0, "is_on_call": true}, {"shift": "צהריים", "count": 5, "hours": 40.0, "is_on_call": false}], "by_day": [{"date": "2026-08-17", "weekday": "יום שני", "count": 4, "hours": 28.0, "on_call": 1}, {"date": "2026-08-18", "weekday": "יום שלישי", "count": 4, "hours": 28.0, "on_call": 1}, {"date": "2026-08-19", "weekday": "יום רביעי", "count": 3, "hours": 24.0, "on_call": 0}, {"date": "2026-08-20", "weekday": "יום חמישי", "count": 4, "hours": 28.0, "on_call": 1}, {"date": "2026-08-21", "weekday": "יום שישי", "count": 3, "hours": 24.0, "on_call": 0}, {"date": "2026-08-22", "weekday": "שבת", "count": 1, "hours": 8.0, "on_call": 0}, {"date": "2026-08-23", "weekday": "יום ראשון", "count": 0, "hours": 0.0, "on_call": 0}], "by_employee": [{"employee": "דנה", "hours": 40.0, "shifts": 5, "on_call": 0, "days": 5}, {"employee": "יוסי", "hours": 36.0, "shifts": 5, "on_call": 1, "days": 5}, {"employee": "רון", "hours": 36.0, "shifts": 5, "on_call": 1, "days": 5}, {"employee": "מיכל", "hours": 28.0, "shifts": 4, "on_call": 1, "days": 4}, {"employee": "אבי", "hours": 0.0, "shifts": 0, "on_call": 0, "days": 0}], "warning_counts": [{"code": "unfilled", "severity": "warning", "count": 5}, {"code": "over_hours", "severity": "warning", "count": 1}, {"code": "overstaffed", "severity": "notice", "count": 2}], "constraint_pressure": {"blocked": 3, "people": 3, "conflicts": 1, "honored": 2}} as never;

export default function Preview() {
  return (
    <div className="management">
      <main className="management-body">
        <div className="management-main">
          <Stats stats={STATS} />
        </div>
      </main>
    </div>
  );
}
