---
type: "query"
date: "2026-08-21T20:07:57.637896+00:00"
question: "i want cllckable questions and theres alweys place that he say somthing like רשמתי את רשימת העובדים ואת ימי הפעילות (ראשון עד חמישי). but does nothing"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Interview Workflow", "Chat-First Frontend"]
---

# Q: i want cllckable questions and theres alweys place that he say somthing like רשמתי את רשימת העובדים ואת ימי הפעילות (ראשון עד חמישי). but does nothing

## Answer

Expanded from original query via graph vocab: [interview, messages, frontend, response, employee, mutated, persistence, chat]. The interview backend already carries options to the Chat-First Frontend, but discarded a single usable option. The false acknowledgement came from Interview Workflow draft updates: past-tense רשמתי was not checked, partial employee and shift items were too strict to record incrementally, and a partial write could hide a dropped claimed field. Fixed those shared paths and verified the backend suite.

## Outcome

- Signal: useful

## Source Nodes

- Interview Workflow
- Chat-First Frontend