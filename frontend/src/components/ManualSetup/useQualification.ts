"use client";

import { useEffect, useState } from "react";

import { qualificationPreview } from "@/services/api";
import type { QualificationStanding } from "@/types";

type Person = { name: string; qualifications: { role: string; last_active: string }[] };

/** The server's view of each dated person's כשירות, from the unsaved rows.
 *
 *  Like the rotation strip, it is re-asked a moment after typing stops and
 *  the stale request is aborted. Nobody dated means nothing to ask and
 *  nothing coloured. */
export function useQualification(employees: Person[]) {
  const [people, setPeople] = useState<Record<string, QualificationStanding>>({});
  const dated = employees.filter((person) => person.name && person.qualifications.some((row) => row.role && row.last_active));
  const key = JSON.stringify(dated);

  useEffect(() => {
    const rows = JSON.parse(key) as Person[];
    if (!rows.length) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      qualificationPreview({ employees: rows }, controller.signal)
        .then((result) => setPeople(result.people))
        .catch(() => { if (!controller.signal.aborted) setPeople({}); });
    }, 400);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [key]);

  return dated.length ? people : {};
}
