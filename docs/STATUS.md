# Forge — Build Status

This document tracks the current build phase, what is implemented, the acceptance
evidence, and the known limitations. It is updated at the end of each major phase, per
the master build prompt's "Deliverables per phase".

## Current phase

**Phase 4 — Tool Runtime** delivered; **Phases 1–3** complete.

Phase 0 (Specification) is complete and lives in the Forge specification workspace
(mirrored conceptually in `docs/`).

## Phase 4 — Tool Runtime

| Build-order item (Phase 4) | Status | Notes |
| --- | --- | --- |
| Tool registry | ✅ | Declarative `ToolSpec` contract + catalog; 12 built-in tools registered and queryable via the catalog API. |
| Filesystem tool | ✅ | `fs.read`/`fs.write`/`fs.list`/`fs.delete`, jailed to the project workspace root; `fs.delete` is destructive (approval-gated). |
| Terminal tool | ✅ | `terminal.run`: argv allow-list, `shell=False`, scrubbed env, timeout, cwd-confined. |
| Git tool | ✅ | `git`: curated **offline** subcommand set with a pinned commit identity; network subcommands refused. |
| Package tool | ✅ | `package.install` (pip/npm) — runnable but **egress-gated**: refused until a host allow-list is granted. |
| HTTP/search tools | ✅ | `http.request` via a deny-by-default egress allow-list; `search.web` declared with a provider seam (configured in Phase 6/9). |
| Database tool | ✅ | `db.query` (read-only) + `db.execute` (destructive, approval-gated) against a project-local SQLite target. |
| Browser tool | ✅ (declared) | `browser.navigate` is a declared contract with `handler=None`; the real browser engine is Phase 15. |
| Tool auditing | ✅ | Every call (including denials) → durable `ToolInvocation` + `AuditEvent`; argument metadata redacted, values truncated. |

All enforcement runs through one path (`ToolRuntime.invoke`): **deny-by-default**
authorization (project grant **and**, for agents, least-privilege `allowed_tools`), input
schema validation, an **approval gate** for destructive tools, execution inside a
**controlled environment** (filesystem jail + egress policy), and output schema validation.
Agents (Phase 3) receive a runtime and call tools via `ctx.call_tool(...)`. Migration
`0004_tool_runtime` is reversible (ADR-0006).

**Known Phase 4 limitations:** the `LocalWorkspaceEnvironment` jails tool *filesystem*
operations and controls *egress*, but does not fully isolate a spawned subprocess — so
command execution (`terminal`/`git`/`package`) is **disabled outside `local`/`development`**
until the container sandbox (Phase 5) implements the same `ExecutionEnvironment` interface.
`browser.navigate` is inert until Phase 15; `search.web` has no provider until Phase 6/9;
`db.*` targets project-local SQLite (richer targets arrive with the sandbox). Tool budget
accounting is wired but nominal until the cost/model runtime (Phases 10/15/20).

## Phase 3 — Agent Runtime

| Build-order item (Phase 3) | Status | Notes |
| --- | --- | --- |
| Agent contract | ✅ | Frozen `Agent` dataclass: identity/role/objective, I/O JSON schemas, tools, model policy, budget, timeout, retry, escalation, verifier. |
| Agent registry | ✅ | Catalog of agents; initial 17-agent roster registered as declared specs + runnable examples. |
| Agent lifecycle | ✅ | `AgentStatus` (created→…→verifying→succeeded/failed/cancelled); every attempt recorded as a durable `AgentExecution`. |
| Context assembly | ✅ | Focused bundle: project goal, run, task inputs, direct-dependency outputs, recent failure signals (isolation, not whole-repo dumps). |
| Agent permissions | ✅ | Per-agent least-privilege `allowed_tools` set (enforced when the tool runtime lands in Phase 4). |
| Agent budgets | ✅ | `AgentBudget` (usd/tokens/seconds); `record_usage` raises `BudgetExceeded` mid-run. |
| Verification contracts | ✅ | Output JSON-Schema check + custom checks; completion requires outputs exist **and** verification passes. |

Agents execute **as task kinds on the Phase 2 durable queue** (ADR-0005), so retries,
dead-lettering, leases, and cancellation apply unchanged. Migration `0003_agent_executions`
is reversible.

**Known Phase 3 limitations:** the roster agents are declared contracts with no executor
yet (they fail loudly if invoked) — the executable agents are deterministic *examples*
used to exercise the framework; model-backed execution arrives with the model runtime
(Phases 10/13). Timeouts are recorded but not yet hard-enforced. Tool permissions are
declared but unenforced until Phase 4.

## Phase 2 — Durable Execution



| Build-order item (Phase 2) | Status | Notes |
| --- | --- | --- |
| Run model | ✅ | `runs` table; pending → running → succeeded/failed/cancelled. |
| Task model | ✅ | `tasks` + `task_dependencies` (DAG); inputs/outputs/checkpoint. |
| State machine | ✅ | Validated transitions in `orchestration/state.py`. |
| Queue | ✅ | Durable DB-backed queue; claim via optimistic concurrency (no external broker). |
| Worker lifecycle | ✅ | `orchestration/worker.py`: handler registry + drain loop + CLI (`python -m forge.orchestration.worker`). |
| Leases / heartbeats | ✅ | `lease_owner`/`lease_expires_at`; reaper reclaims crashed workers' tasks. |
| Retry policies | ✅ | Bounded `max_attempts` with exponential backoff; exhaustion → dead-letter. |
| Cancellation | ✅ | Propagates to child tasks; cooperative for running tasks. |
| Checkpoints | ✅ | Durable `checkpoint` JSON per task for resume-without-restart. |

Reliability invariants exercised: **resume-after-crash** (lease reaping), **idempotent
bounded retries**, **cancellation propagation**, **durable state** (a fresh session/worker
resumes an in-flight run), and **validated transitions**. Migration `0002_orchestration`
is reversible.

**Known Phase 2 limitations:** execution is single-process-friendly and DB-polling based
(no `SELECT ... FOR UPDATE SKIP LOCKED` yet — claim uses portable optimistic concurrency);
budgets/circuit-breakers are specified but deferred to Phases 8/10; runs/tasks are exposed
via API + worker but not yet surfaced in the UI (the command-center "Tasks" area remains a
roadmap placeholder for now).

## Phase 1 — Foundation



| Build-order item (Phase 1) | Status | Notes |
| --- | --- | --- |
| Repository structure | ✅ | Monorepo: `backend/`, `frontend/`, `docs/` (ADR-0003). |
| Development environment | ✅ | `docker-compose` (Postgres), `Makefile`, `.env.example`, CI. |
| Configuration system | ✅ | `pydantic-settings`, validated at startup, fail-fast in prod. |
| Core database | ✅ | Users, workspaces, memberships (RBAC), projects, audit events. |
| API foundation | ✅ | Versioned `/api/v1`, OpenAPI, error envelope, correlation IDs, pagination. |
| Authentication | ✅ | JWT + bcrypt; register/login/me; personal workspace provisioning. |
| Workspace/project model | ✅ | Workspace-scoped RBAC; project CRUD with optimistic concurrency. |
| UI shell | ✅ | React command center: login, Command Center, Projects, Settings, roadmap placeholders. |

Cross-cutting invariants exercised: **durable state** (relational core + versioned
projects, ADR-0002), **auditability** (atomic `AuditEvent` trail with correlation IDs),
**least privilege** (workspace membership + role checks on every request),
**verified completion** (35 backend tests, browser QA screenshots).

## Acceptance evidence

- **Backend tests:** `cd backend && pytest` → **98 passed** (35 foundation + 20
  durable-execution + 15 agent-runtime + 28 tool-runtime). The tool-runtime tests cover:
  deny-by-default authorization, the filesystem jail (path-escape refusal), input/output
  schema validation, the destructive-op approval gate (and `auto_approve` grants),
  read/write SQLite tools, HTTP egress control (denied by default; allowed for an
  allow-listed host, exercised against a local server), the terminal allow-list, offline
  `git`, egress-gated package installs, honest failures for `search`/`browser`, argument
  redaction + audit recording, and the agent↔tool least-privilege integration end-to-end.
- **Lint:** `ruff check` → clean.
- **Migrations:** `alembic upgrade head` and `alembic downgrade base` succeed across all
  four migrations on a fresh database (reversible).
- **Frontend:** unchanged this phase; `npm run build` still type-checks and builds.
- **End-to-end:** Phase 4 an agent (`example.fs_roundtrip`) drained by a standalone worker
  wrote and read a file through the tool runtime under least privilege, producing two
  durable, audited `ToolInvocation` rows tied to the run/task/agent.

## Known limitations

- **SQLite in this environment.** The Docker daemon was unavailable during the build, so
  verification ran against SQLite. Postgres is the intended dev/prod database
  (`docker compose up -d db`); CI is configured to also run against Postgres. See
  ADR-0001 for the divergence-risk mitigations.
- **Auth is single-token.** No refresh tokens, rotation, or logout revocation yet;
  access tokens are short-lived. Password reset and email verification are out of scope
  for this slice.
- **Runs/tasks are backend + API + worker only.** The command-center "Tasks" area is not
  yet wired to the orchestration API and remains a roadmap placeholder.
- **Command-center placeholders.** Areas whose subsystems are not built (Agents, Research,
  …) render an explicit "Planned — Phase N" page rather than fake data.
- **Rate limiting and idempotency keys** are specified (`22_API`) but not yet enforced;
  scaffolding for the error code exists.

## Next phase

**Phase 5 — Sandbox**: a container-backed `ExecutionEnvironment` implementing the Phase 4
tool seam, with container lifecycle, resource limits, a real network policy, a secret
broker, per-project workspace isolation, and snapshot/reset — so command-spawning tools
(`terminal`/`git`/`package`) and richer database/browser targets run under full isolation
rather than the local workspace environment.
