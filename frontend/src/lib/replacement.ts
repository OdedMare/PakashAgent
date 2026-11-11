/** The sentences the replacement surfaces send to the agent.
 *
 *  One wording, because the server reads these back in code
 *  (`bl/absence/selections.py`, `bl/absence/reader.py`) to build the plan
 *  without a model round. Change it here and there together. */

// "לא זמין/ה" first and the default: most of the time the manager only
// knows the person is out, not why, and should not have to pick a reason.
export const ABSENCE_REASONS = ["לא זמין/ה", "חולה", "בחופשה", "במילואים", 'בחו"ל'] as const;
export type AbsenceReason = typeof ABSENCE_REASONS[number];

export function selectionSentence(employee: string, shift: string, date: string, replacing?: string): string {
  return `אני בוחר את ${employee} למשמרת ${shift} בתאריך ${date}${replacing ? ` במקום ${replacing}` : ""}.`;
}

export function absenceSentence(employee: string, reason: AbsenceReason, from: string, to: string): string {
  return from === to ? `${employee} ${reason} בתאריך ${from}.` : `${employee} ${reason} מ-${from} עד ${to}.`;
}
