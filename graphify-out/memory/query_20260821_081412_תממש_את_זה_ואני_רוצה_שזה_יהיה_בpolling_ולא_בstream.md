---
type: "query"
date: "2026-08-21T08:14:12.433730+00:00"
question: "תממש את זה ואני רוצה שזה יהיה בpolling ולא בstream כמו שעכשוי"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Interview Workflow", "Scheduling Persistence Schema", "OpenAI-Compatible JSON Client", "Agent Decides; Code Audits"]
---

# Q: תממש את זה ואני רוצה שזה יהיה בpolling ולא בstream כמו שעכשוי

## Answer

Expanded via graph vocab: [interview, messages, conversational, workflow, schema, store, runtime, client, agent, audit]. Implemented sparse draft_update responses merged server-side, model context limited to the latest assistant/user exchange plus draft/resolved/open-points state, async process-local interview generation persisted as processing/error in session pending JSONB, GET polling from the React hook, and a dedicated retry endpoint that does not duplicate user input. Full transcript remains stored and returned to the UI. No DB migration. Verified with 696 backend tests, focused frontend ESLint, and a successful Next.js production build.

## Outcome

- Signal: useful

## Source Nodes

- Interview Workflow
- Scheduling Persistence Schema
- OpenAI-Compatible JSON Client
- Agent Decides; Code Audits