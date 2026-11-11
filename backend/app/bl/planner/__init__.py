"""What the manager chat's question path shares with the no-model reader.

The model-driven question loop (`/ask`) was replaced by the manager chat;
what is left here is what the chat still reads: the question and tool-call
shapes it answers in, and the deterministic answers it gives without a
model (`fallback_answers.py`, over `bl/tools` and `bl/intent`). Nothing here
writes, and no answer carries an operation (D19).

| Module | Owns |
|---|---|
| `fallback_answers.py` | Replacement answers with no model |
| `schema.py`, `shaping.py` | The question and tool-call schema; shaping a question |
| `trace.py` | The steps an answer reports |
"""
