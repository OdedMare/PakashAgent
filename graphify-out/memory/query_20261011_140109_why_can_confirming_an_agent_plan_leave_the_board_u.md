---
type: "query"
date: "2026-10-11T14:01:09.977530+00:00"
question: "Why can confirming an agent plan leave the board unchanged?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["Change Confirmation Surface", "Chat-First Frontend"]
---

# Q: Why can confirming an agent plan leave the board unchanged?

## Answer

Expanded graph vocabulary: confirmation applied change schedule frontend persistence response retry. The graph identifies Change Confirmation Surface and Chat-First Frontend as approval entry points. Current source verification found swallowed overview refresh errors, independent board reads, and out-of-order overview responses. Approval now verifies an applied stored plan, recovers or retries lost responses once using the same message id, awaits fresh board and overview reads, and offers a read-only refresh retry after a saved plan. Added eleven hook regression tests; relevant backend workflows passed.

## Outcome

- Signal: useful

## Source Nodes

- Change Confirmation Surface
- Chat-First Frontend