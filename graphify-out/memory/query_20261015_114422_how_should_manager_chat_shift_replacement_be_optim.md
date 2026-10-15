---
type: "architecture"
date: "2026-10-15T11:44:22.697165+00:00"
question: "How should manager-chat shift replacement be optimized for LLM cost without weakening approval safety?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Conversational Schedule Changes", "Two-Step Change Contract", "Agent Decides; Code Audits", "OpenAI-Compatible JSON Client"]
---

# Q: How should manager-chat shift replacement be optimized for LLM cost without weakening approval safety?

## Answer

Route only unambiguous one-employee replacement or absence lookups with a resolved date through the existing deterministic employee_state and find_replacements tools. Preserve absence constraints as conversation task context. Return explicit selections, ambiguous requests, and no-candidate cases to the existing model proposal, code audit, and atomic approval flow. Persist aggregate prompt/completion/total tokens and model-round count on each generated chat turn.

## Outcome

- Signal: useful

## Source Nodes

- Conversational Schedule Changes
- Two-Step Change Contract
- Agent Decides; Code Audits
- OpenAI-Compatible JSON Client