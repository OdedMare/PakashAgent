"""Database definition applied during repository initialization.

The tables the intro interview needs, plus `teams` — the workspace every
other row hangs off — plus the scheduling half: `schedules`, `shift_slots`,
`assignments`, `availability`, and the append-only `change_log`. Each of
those carries `team_id` from the day it is created, because retrofitting a
tenant key onto a populated table is the expensive version of this.

The scheduling tables encode two decisions directly. `assignments.reason`
exists because every assignment carries the agent's reasoning (D8), and
`change_log` is append-only because it is the only history the system keeps
(D4) — there are no version rows and no rollback.

The COMMIT after each independent block is the AiSummryIO convention and is
load-bearing: the whole script is sent as one simple-query message, which
Postgres implicitly wraps in a single transaction unless the text commits
along the way. Without the checkpoints, one guarded migration failing on a
particular database's data rolls back every unrelated statement that already
succeeded in the same call. Add a new guarded migration after its own COMMIT.
"""

from app.dal.repository.ddl.agent import AGENT_DDL
from app.dal.repository.ddl.employees import EMPLOYEE_DDL
from app.dal.repository.ddl.scheduling import SCHEDULING_DDL
from app.dal.repository.ddl.workspace import WORKSPACE_DDL
from app.dal.repository.chat import CHAT_DDL

# Applied in this order: every later block references `teams`, and the
# employee tables reference the scheduling ones.
SCHEMA = WORKSPACE_DDL + SCHEDULING_DDL + EMPLOYEE_DDL + AGENT_DDL + CHAT_DDL
