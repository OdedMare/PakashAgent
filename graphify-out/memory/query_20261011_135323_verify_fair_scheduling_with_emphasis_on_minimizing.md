---
type: "query"
date: "2026-10-11T13:53:23.456364+00:00"
question: "Verify fair scheduling with emphasis on minimizing each employee night shifts"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Schedule Generation", "Agent Decides; Code Audits"]
---

# Q: Verify fair scheduling with emphasis on minimizing each employee night shifts

## Answer

Expanded from original Hebrew request via graph vocabulary: schedule scheduling assignments. Graph Schedule Generation points to scheduler flow; verified current source because graph paths predate src layout. Changed backend/src/app/bl/audit/roster.py to count night flags, overnight shifts and starts at 22:00-05:59 using effective slot times. Shared scheduler/fairness.py now detects safe night transfers or day-night exchanges respecting audit and pins, prioritizes current night variance then historical night variance then current hours. Both generate and generate_span request one model repair and surface uneven_nights when still improvable. No global minimum guarantee; model still decides. Full backend suite passed 1162 tests with 12 skips and two pre-existing manager_chat failures reproduced on baseline 29a5bb0. No real model or production schedule was tested.

## Outcome

- Signal: useful

## Source Nodes

- Schedule Generation
- Agent Decides; Code Audits