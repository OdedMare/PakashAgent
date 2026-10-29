# Real schedule file formats

> These samples define the layout `bl/export.py` writes (Sample A) and are
> the importer's first fixtures (`tests/test_importer.py`). Since
> [D42](DECISIONS.md) the importer is not limited to them: any shape is a
> `Layout` (`bl/importer/layout.py`) — both samples turned on their side,
> people down the side with shift names in the cells, weekday templates,
> weeks stacked on one sheet.

Derived from two schedule files supplied by the boss. They are the evidence
behind [D7](DECISIONS.md#d7--import-infers-layout-boss-confirms) and
[D9](DECISIONS.md#d9--shift-vocabulary-is-per-workplace), and they should become
the importer's first two test fixtures.

**The headline finding: the two files are structurally different from each
other.** Not cosmetically — the axes mean different things. Any importer built
for one will fail on the other. This is why there is no template.

---

## Sample A — shift-major, dense

```
            │ 15/6/25 │ 16/6/25 │ 17/6/25 │ 18/6/25 │ 19/6/25
  משמרות    │  ראשון  │   שני   │  שלישי  │  רביעי  │  חמישי
────────────┼─────────┼─────────┼─────────┼─────────┼─────────
   בוקר     │ שובל ק. │ אלמוג ע.│ אורי א. │ אלמוג ע.│ תאיר ג.
  צהריים    │ ניצן ש. │ ניצן ש. │ אלמוג ע.│ סאלי א. │ סאלי א.
```

- **Columns** = dates (`d/M/yy`), with a Hebrew weekday name in a second header row.
- **Rows** = shifts (`משמרות` = "shifts" labels the row header column).
- **Cells** = one assigned person's name.
- Dense — effectively every cell filled.
- 2 shifts: בוקר, צהריים.

## Sample B — person-major, sparse, nested header

```
        │      2.2 ראשון       │      3.2 שני         │  …
        │ בוקר │צהריים│כונן לילה│ בוקר │צהריים│כונן לילה│
────────┼──────┼──────┼────────┼──────┼──────┼────────┤
        │      │מאור נ│        │      │מאור נ│        │
        │נועה ר│      │        │      │      │        │
        │      │      │        │      │      │        │
        │      │יערה ש│        │      │      │        │
        │      │      │        │      │לא זמינה│      │
```

- **Columns** = date **subdivided into three shift sub-columns**. The column axis
  is `date × shift`, nested, with merged header cells on the date row.
- **Rows** = per-person lanes. A person's name appears in the cells where they are
  placed.
- **Sparse** — the large majority of cells are empty.
- 3 shifts: בוקר, צהריים, **כונן לילה** (on-call night).
- **Availability lives in the same grid**: `לא זמינה` / `לא זמין` appears as a cell
  value alongside assignment names.

---

## Sample C — the unit's own sheet: people down the side, `date × shift` across, a tab per month

```
    │  06/10/2024 (merged ×3)  │  07/10/2024 (merged ×3)  │ …
    │        ראשון             │          שני             │
 שם │ בוקר │ צהריים │ לילה     │ בוקר │ צהריים │ לילה     │
────┼──────┼────────┼──────────┼──────┼────────┼──────────┤
הלל רדובסקי │      │        │          │ רוני │        │          │
עלמה שדה    │ בית  │  בית   │  בית     │      │ עלמה   │          │
גלי רותם    │      │ גלי חפיפה│        │      │        │          │
```

- **Rows** = people, their full name in column A, under a header cell `שם`.
- **Columns** = one date merged across three shift sub-columns, with a
  weekday row between the date and the shift names. The dates sit in row 1
  on one tab and in row 2 under a title on another.
- **Cells**: the person's *first* name where they work; `בית` across a
  stretch at home and `חופש` on leave (both absences); `<name> חפיפה` or
  `<name>-חפיפה` on a handover shift — the person works it, and the word is
  kept as the row's note.
- **Dates are written either way round.** One copy writes `13/10/2024`,
  another, saved on an American locale, `10/13/2024`. The header line
  decides which (a part above 12, else the order that runs on day to day).
- **Width**: a tab per month (אוקטובר, נובמבר, דצמבר, ינואר 25), or one tab
  carrying the whole year out to column AEB. The preview opens on the month
  covering today and takes any other run of dates.
- Cell colours (purple for a shift, grey for home) and the name column's
  colours are presentation only; the text says the same thing.

---

## What the importer must therefore do

1. **Infer axis semantics, not just orientation.** Which axis is time; whether
   shift is nested under date (B) or is its own axis (A); whether the non-time
   lanes are shifts (A) or people (B).

2. **Classify every cell**, don't just read it:
   - a person's name → an assignment
   - `לא זמין` / `לא זמינה` (and variants) → an unavailability marker
   - empty → no data

   Availability and assignments **coexist in one sheet**. Do not assume separate
   files or sheets for them.

3. **Handle merged header cells.** Both samples use them; Sample B depends on
   them to express the nested date→shift header.

4. **Parse Hebrew as data.** Weekday names (ראשון … שבת), shift names,
   availability markers, and **two date formats** — `d/M/yy` (A) and `d.M` (B),
   the latter with no year, which must be resolved from surrounding context or
   the period being imported.

5. **Match shift headers against the interview's declared vocabulary** ([D9](DECISIONS.md#d9--shift-vocabulary-is-per-workplace)),
   rather than inferring shift names from scratch.

6. **Emit an interpretation for confirmation** before committing — e.g. *"8 people,
   1.2–8.2, 3 shifts/day, 4 unavailability marks"* — per [D7](DECISIONS.md#d7--import-infers-layout-boss-confirms).

## Fixtures

Rebuild both samples as `.xlsx` fixtures under `backend/tests/fixtures/` and assert
the inferred interpretation for each. They are the regression suite for layout
inference — the riskiest part of the build. Add a third real file as a fixture
when one becomes available.
