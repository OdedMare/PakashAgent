type ReservePreview = { employee: string; shifts: number };

/** The confirmation shown before reservists with future work are disabled. */
export function reserveFutureWarning(previews: ReservePreview[]): string {
  const affected = previews.filter((row) => row.shifts > 0);
  if (!affected.length) return "";
  const total = affected.reduce((sum, row) => sum + row.shifts, 0);
  const count = total === 1 ? "משמרת עתידית אחת" : `${total} משמרות עתידיות`;
  const people = affected.map((row) => `${row.employee} — ${row.shifts}`).join("\n");
  return `שימו לב: למילואימניקים יש ${count}:\n${people}\n\nהכיבוי לא מוחק שיבוצים שכבר נבנו.`;
}
