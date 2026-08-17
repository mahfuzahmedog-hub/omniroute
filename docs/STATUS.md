# Forge — Build Status

This document tracks the current build phase, what is implemented, the acceptance
evidence, and the known limitations. It is updated at the end of each major phase, per
the master build prompt's "Deliverables per phase".

## Current phase

**Phase 2 — Durable Execution** delivered (backend/engine); **Phase 1 — Foundation** complete.

Phase 0 (Specification) is complete and lives in the Forge specification workspace
(mirrored conceptually in `docs/`). The repository was previously empty, so this is the
first implementation slice.

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

- **Backend tests:** `cd backend && pytest` → **55 passed** (35 foundation + 20
  durable-execution). Covers health, auth (success + failure paths), workspace RBAC,
  project CRUD, workspace isolation, pagination, optimistic-concurrency conflict, the
  error envelope, the audit trail, state-machine transitions, dependency gating, lease
  claim exclusivity, retry→backoff→dead-letter, crash recovery via lease reaping,
  cancellation propagation, and resume-after-restart.
- **Lint:** `ruff check` → clean.
- **Migrations:** `alembic upgrade head` and `alembic downgrade base` succeed across both
  migrations on a fresh database (reversible).
- **Frontend:** `npm run build` → type-checks and builds (0 errors).
- **End-to-end:** live uvicorn + Vite dev server exercised via Playwright (Phase 1 UI);
  live API + standalone worker process draining a dependency-gated run to `succeeded`
  (Phase 2). Screenshots in [`docs/screenshots/`](screenshots/).

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

**Phase 3 — Agent Runtime**: the agent contract, registry, lifecycle, context assembly,
per-agent permissions/budgets, and verification contracts — executed as task kinds on the
durable queue built in Phase 2.
