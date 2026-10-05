---
type: "query"
date: "2026-10-05T10:40:31.410171+00:00"
question: "How does the current manager chat connect to schedule questions and changes?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Chat-First Frontend", "Change Confirmation Surface", "Two-Step Change Contract"]
---

# Q: How does the current manager chat connect to schedule questions and changes?

## Answer

Expanded graph vocabulary: agent chat schedule shift change confirm. Graph nodes Chat-First Frontend (frontend/CLAUDE.md), Change Confirmation Surface (frontend/CLAUDE.md), and Two-Step Change Contract (backend/app/api/CLAUDE.md) describe a chat-oriented frontend and propose-then-confirm changes. These locations have no line-level source_location in the graph. Current source inspection corroborates separate ask and propose endpoints, a single latest answer and proposal in the UI, and pending clarification context rather than a persistent conversation transcript. The desired redesign needs a unified composer, conversation history, and an explicit decision on write authority.

## Outcome

- Signal: useful

## Source Nodes

- Chat-First Frontend
- Change Confirmation Surface
- Two-Step Change Contract