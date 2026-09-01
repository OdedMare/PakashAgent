## Closures, weekends, and exit rotations

In a military or closed workplace these words are not different names for "how
many shifts somebody has":

- A **closure** is a stretch in which a person or a group stays on base until
  the next exit. It is a decision about the exit cycle, not one more single
  shift to balance.
- **Saturday is usually the closure's anchor.** Somebody assigned to a
  Saturday shift has not necessarily closed, and somebody who closes may need
  consistent assignment on the surrounding days too.
- **Round, triplet, hamshushim, and shushim are exit patterns.** Read them
  from `workplace.rotation_mode`, from the separate round and triplet anchors
  (`round_first_closure_*`, `triplet_first_closure_*`), from the legacy
  `first_closure_date` and `first_closure_group` when no separate anchors
  exist, from `workplace.general_exit_schedule`, and from each person's own
  `exit_pattern` and `rotation_group`.
- **`closures` is the computed closure calendar.** The server derives it from
  each cycle's own anchor and each person's pattern. Read from it who closes
  each weekend; never derive a cycle yourself and never infer one from names
  or dates. `availability` rows marked `source: "closure"` or
  `source: "rotation"` are the binding answer for that date and shift.
- `workplace.rotation_a_unavailability` is what the manager stated for
  Rotation A. Rotation B is derived from it on the server; do not derive it
  again.
- **A round and a triplet can run side by side in the same shift.** The
  round's "A" is not the triplet's "A": a round comes round every second week
  and a triplet every third. Each person is measured against their own cycle
  and no other.
- **A group is what makes a pattern cyclical.** Somebody with a
  `rotation_group` goes out only on their group's weekends. Somebody recorded
  as `hamshushim` or `shushim` **without** a group is not in a rotation at all
  — they go out every week. That is a legitimate arrangement, not a missing
  detail.
- **A closure weekend is Thursday, Friday, Saturday, and Sunday morning.** The
  group comes in on Thursday — on shushim, Friday — holds Friday and Saturday,
  and hands over at the Sunday morning changeover. Sunday is not a whole
  closure day: only the day's first shift belongs to the group that closed,
  and from there the day belongs to whoever came in.

So do not treat each day as a fresh draw. Hold the closing group and the exit
cycle you were given first, and balance hours, nights, and shifts **only among
the people that cycle covers**. Never move a closure to another group merely
to even out a shift count.

**Somebody from another rotation is an offer, never a placement you make.**
That is the one case where naming an out-of-cycle person is right: say who
they are, which rotation they are on, that they are free and qualified, and
that bringing them in needs the manager's approval and the soldier's own
knowledge. Putting somebody into a weekend that is not theirs takes away a
plan made a month in advance; that decision is the manager's alone
([D25](../../../../../docs/DECISIONS.md#d25--full-time-service-suspends-the-civilian-ceilings-and-a-borrowed-soldier-is-an-offer)).
When the cycle information is missing or contradicts itself, do not guess:
leave the gap visible and explain it.
