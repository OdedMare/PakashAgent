import type { AgentAnswer, Proposal, Simulation } from "@/types";

/** One cell the agent has said something about, and why it is lit.
 *
 *  `shift`+`date` is the cell; `employee` narrows it to one card inside a
 *  cell holding several. Empty `employee` lights the whole cell — which is
 *  what a gap or a coverage remark is actually about. */
export interface AgentTouch {
  shift: string;
  date: string;
  employee: string;
  /** Which card in the side column this came from. The board colours off
   *  it, so a proposal and a simulation can never look like each other —
   *  the same separation D20 draws on the panels themselves. */
  origin: "proposal" | "simulation" | "answer";
  /** What the agent said about this cell, shown on hover. */
  note: string;
}

/** The cell key the board indexes on. Shift and date, never the person:
 *  a cell is a place on the grid and two people may stand in it. */
export function touchKey(shift: string, date: string): string {
  return `${shift}|${date}`;
}

/** Everything the agent is currently pointing at, as a map by cell.
 *
 *  **This reads state; it never writes and never proposes.** A highlight is
 *  the visual half of a sentence already on screen in the side column — the
 *  manager still sends, the agent still proposes, and they still confirm
 *  with their reason (D8/D12). Lighting a cell adds no path to `apply`, and
 *  that is why deriving it from what is already rendered, rather than from
 *  any new field on the wire, is the right shape: there is nothing here that
 *  a confirmation could read.
 *
 *  Ordered proposal last so it wins a cell contested by two sources. A
 *  proposal is the one with a confirm button attached, so it is the one the
 *  manager is being asked about; a simulation and an answer are both things
 *  they are still only reading.
 */
export function collectTouches(input: {
  simulation: Simulation | null;
  proposal: Proposal | null;
  answer: AgentAnswer | null;
}): Map<string, AgentTouch[]> {
  const touches: AgentTouch[] = [
    ...fromSimulation(input.simulation),
    ...fromAnswer(input.answer),
    ...fromProposal(input.proposal),
  ];

  const byCell = new Map<string, AgentTouch[]>();
  for (const touch of touches) {
    if (!touch.shift || !touch.date) continue;
    const key = touchKey(touch.shift, touch.date);
    const existing = byCell.get(key);
    if (existing) existing.push(touch);
    else byCell.set(key, [touch]);
  }
  return byCell;
}

/** A simulation's operations, including both ends of a swap.
 *
 *  `with_shift`/`with_date` fall back to the operation's own cell because a
 *  swap inside one slot omits them — the two people are already in the same
 *  place, and dropping that end would light half of a two-sided change. */
function fromSimulation(simulation: Simulation | null): AgentTouch[] {
  if (!simulation) return [];
  const touches: AgentTouch[] = [];
  for (const operation of simulation.operations ?? []) {
    touches.push({
      shift: operation.shift,
      date: operation.date,
      employee: operation.employee,
      origin: "simulation",
      note: operationNote(operation.action, operation.employee),
    });
    if (operation.with_employee) {
      touches.push({
        shift: operation.with_shift || operation.shift,
        date: operation.with_date || operation.date,
        employee: operation.with_employee,
        origin: "simulation",
        note: operationNote(operation.action, operation.with_employee),
      });
    }
  }
  return touches;
}

/** A proposal's operations — the same shape, a different colour.
 *
 *  Kept as its own function rather than sharing one with the simulation:
 *  they carry the same fields today and mean different things, and a single
 *  helper taking an `origin` argument is how the two would quietly become
 *  interchangeable. */
function fromProposal(proposal: Proposal | null): AgentTouch[] {
  if (!proposal) return [];
  const touches: AgentTouch[] = [];
  for (const operation of proposal.operations ?? []) {
    touches.push({
      shift: operation.shift,
      date: operation.date,
      employee: operation.employee,
      origin: "proposal",
      note: operation.reason || operationNote(
        operation.action, operation.employee,
      ),
    });
    if (operation.with_employee) {
      touches.push({
        shift: operation.with_shift || operation.shift,
        date: operation.with_date || operation.date,
        employee: operation.with_employee,
        origin: "proposal",
        note: operation.reason || operationNote(
          operation.action, operation.with_employee,
        ),
      });
    }
  }
  return touches;
}

/** What an answer looked at, read off the tools it actually ran.
 *
 *  **An answer carries no operations and this does not invent any.** The
 *  cells come from the arguments the agent passed to its own read-only
 *  tools — the shift and date it asked about — so what lights up is where it
 *  looked, never a change it is proposing. That distinction is the whole of
 *  D19, and it is why these render in their own neutral colour rather than
 *  in the proposal's.
 *
 *  Only steps that succeeded are read: a tool call that failed did not look
 *  anywhere, and lighting its arguments would show the manager a search that
 *  never happened.
 */
function fromAnswer(answer: AgentAnswer | null): AgentTouch[] {
  if (!answer) return [];
  const touches: AgentTouch[] = [];
  for (const step of answer.steps ?? []) {
    if (!step.ok) continue;
    const args = step.arguments ?? {};
    const shift = stringArg(args, "shift_name") || stringArg(args, "shift");
    const date = stringArg(args, "day") || stringArg(args, "date");
    if (!shift || !date) continue;
    touches.push({
      shift,
      date,
      employee: stringArg(args, "employee"),
      origin: "answer",
      note: "הסוכן בדק את המשמרת הזו כדי לענות",
    });
  }
  return touches;
}

function stringArg(args: Record<string, unknown>, name: string): string {
  const value = args[name];
  return typeof value === "string" ? value.trim() : "";
}

function operationNote(action: string, employee: string): string {
  if (action === "remove") return `${employee} — הסוכן מציע להוריד מכאן`;
  if (action === "swap") return `${employee} — חלק מהחלפה שהסוכן מציע`;
  return `${employee} — הסוכן מציע לשבץ לכאן`;
}
