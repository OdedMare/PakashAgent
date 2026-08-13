# Graph Report - .  (2026-08-12)

## Corpus Check
- Corpus is ~5,985 words - fits in a single context window. You may not need a graph.

## Summary
- 108 nodes · 114 edges · 23 communities (19 shown, 4 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Import and Layout Inference
- Conversational Schedule Changes
- Scheduling Runtime Architecture
- URL and Schema Normalization
- Backend Error Hierarchy
- Product Capabilities
- Advisory Rules and UI
- Layered Backend Build Plan
- Application Settings
- Live Runtime Settings
- Employee Read-Only Access
- Agent Error Concept
- Backend Project Configuration

## God Nodes (most connected - your core abstractions)
1. `PakashAgent` - 10 edges
2. `D3 Agent Decides; Code Only Audits` - 8 edges
3. `D7 Import Infers Layout, Boss Confirms` - 8 edges
4. `AppError` - 7 edges
5. `Advisory Checker` - 5 edges
6. `OpenAI-Compatible JSON Client` - 5 edges
7. `D8 Two Reasons, Both Required` - 5 edges
8. `Sample B Person-Major Sparse Nested Layout` - 5 edges
9. `Axis Semantics Inference` - 5 edges
10. `Settings` - 4 edges

## Surprising Connections (you probably didn't know these)
- `PakashAgent` --references--> `Agent Decides; Code Audits`  [EXTRACTED]
  README.md → backend/app/bl/CLAUDE.md
- `PakashAgent` --references--> `PakashAgent Build Plan`  [EXTRACTED]
  README.md → docs/BUILD_ORDER.md
- `PakashAgent` --references--> `D3 Agent Decides; Code Only Audits`  [EXTRACTED]
  README.md → docs/DECISIONS.md
- `Pure Python Advisory Audit` --references--> `D3 Agent Decides; Code Only Audits`  [EXTRACTED]
  backend/CLAUDE.md → docs/DECISIONS.md
- `Per-Workplace Shift Vocabulary` --references--> `D9 Shift Vocabulary Is Per-Workplace`  [EXTRACTED]
  backend/CLAUDE.md → docs/DECISIONS.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **PakashAgent Four-Step Product Flow** — readme_intro_interview, readme_shift_loading_and_generation, readme_schedule_import, readme_conversational_changes [EXTRACTED 1.00]
- **Agent Judgment with Advisory Audit Flow** — backend_app_bl_claude_schedule_generation, backend_app_bl_claude_advisory_checker, backend_app_api_claude_advisory_warning_response, frontend_claude_non_blocking_warning_banners [INFERRED 0.95]
- **Importer Layout Evidence and Mechanisms** — docs_file_formats_sample_a_shift_major_dense, docs_file_formats_sample_b_person_major_sparse, docs_file_formats_axis_semantics_inference, docs_file_formats_cell_classification, docs_file_formats_confirmation_interpretation [EXTRACTED 1.00]

## Communities (23 total, 4 thin omitted)

### Community 0 - "Import and Layout Inference"
Cohesion: 0.22
Nodes (14): Two-Step Import Contract, Layout Inference Importer, Confirm Before Import Persistence, Importer Fixture Strategy, D6 Boss Can Author or Generate, D7 Import Infers Layout, Boss Confirms, D9 Shift Vocabulary Is Per-Workplace, Axis Semantics Inference (+6 more)

### Community 1 - "Conversational Schedule Changes"
Cohesion: 0.18
Nodes (13): Two-Step Change Contract, Conversational Change Workflow, Schedule Generation, Assignments with Agent Reason, Living Schedule, complete_json, Response-Format Degradation Ladder, Invalid JSON Parse Retry (+5 more)

### Community 2 - "Scheduling Runtime Architecture"
Cohesion: 0.18
Nodes (12): Advisory Checker, Agent Decides; Code Audits, Interview Workflow, Runtime Override Store, Data Access Contract, Scheduling Persistence Schema, Connection Reuse Cache, Local Server Accommodations (+4 more)

### Community 3 - "URL and Schema Normalization"
Cohesion: 0.23
Nodes (11): extract_url_schema(), normalize_database_schema(), normalize_database_url(), normalize_http_url(), normalize_llm_base_url(), Accept a pasted endpoint, not just the base.      Users copy the URL they see in, The schema a JDBC-style URL asks for, or "" when it names none.      Lets a past, Validate a schema name. Empty means "use the server default". (+3 more)

### Community 4 - "Backend Error Hierarchy"
Cohesion: 0.27
Nodes (10): AgentError, AppError, AuthError, ConflictError, NotFoundError, Error types leaving the backend.  Messages are Hebrew: they reach a Hebrew-speak, Anything the agent or the model layer failed to do.      The error type everythi, The process is alive but cannot accept work.      503 rather than 500: nothing r (+2 more)

### Community 5 - "Product Capabilities"
Cohesion: 0.22
Nodes (9): Cross-Cutting Infrastructure, AiSummryIO, Conversational Schedule Changes, Hebrew RTL Product, Intro Interview, Layered FastAPI Postgres Architecture, PakashAgent, Schedule Import from Excel or Documents (+1 more)

### Community 6 - "Advisory Rules and UI"
Cohesion: 0.29
Nodes (8): Advisory Warning Response, Pure Python Advisory Audit, D1 Hard and Soft Rules, D2 Rules Stay Natural Language, D3 Agent Decides; Code Only Audits, Chat-First Frontend, Non-Blocking Warning Banners, RTL Schedule Grid

### Community 7 - "Layered Backend Build Plan"
Cohesion: 0.33
Nodes (6): HTTP Layer, PakashAgent Backend Architecture, Business Logic Layer, Data Access Layer, PakashAgent Build Plan, Python Version Resolution

### Community 8 - "Application Settings"
Cohesion: 0.40
Nodes (4): Environment defaults; UI overrides are applied by RuntimeSettingsStore., Env-derived DEFAULTS. Values the boss can edit in the UI live in     common.runt, Settings, BaseSettings

## Knowledge Gaps
- **22 isolated node(s):** `pakash-backend`, `Intro Interview`, `Shift Loading and Generation`, `Schedule Import from Excel or Documents`, `Conversational Schedule Changes` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **4 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Advisory Checker` connect `Scheduling Runtime Architecture` to `Advisory Rules and UI`?**
  _High betweenness centrality (0.099) - this node is a cross-community bridge._
- **Why does `PakashAgent` connect `Product Capabilities` to `Scheduling Runtime Architecture`, `Advisory Rules and UI`, `Layered Backend Build Plan`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `Interview Workflow` connect `Scheduling Runtime Architecture` to `Import and Layout Inference`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **What connects `pakash-backend`, `Intro Interview`, `Shift Loading and Generation` to the rest of the system?**
  _22 weakly-connected nodes found - possible documentation gaps or missing edges._