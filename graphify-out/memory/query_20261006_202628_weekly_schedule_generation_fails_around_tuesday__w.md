---
type: "query"
date: "2026-10-06T20:26:28.885659+00:00"
question: "Weekly schedule generation fails around Tuesday; what should be done?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Schedule Generation", "OpenAI-Compatible JSON Client"]
---

# Q: Weekly schedule generation fails around Tuesday; what should be done?

## Answer

Expanded from original query via vocab: schedule generation generate retry error audit. Graph Schedule Generation and OpenAI-Compatible JSON Client gave orientation but references predate current src tree. Current source inspection and scripted model reproduction show SpanGenerator discards the accepted first attempt if the repair model call raises, at backend/src/app/bl/scheduler/span.py:163-164. Recommend retaining audited first draft with explicit warnings on recoverable repair failure. The checkpointed board job can resume unfinished spans; manager chat generation is a separate preview path. Local Docker backend uses old /app/app structure and responds 404 to agent/chats; no failed generation record was found in its database. Actual user failure cause is unconfirmed without error text.

## Outcome

- Signal: useful

## Source Nodes

- Schedule Generation
- OpenAI-Compatible JSON Client