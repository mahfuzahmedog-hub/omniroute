# Forge — Build Status

This document tracks the current build phase, what is implemented, the acceptance
evidence, and the known limitations. It is updated at the end of each major phase, per
the master build prompt's "Deliverables per phase".

## Current phase

**Phase 1 — Foundation** (in progress → first slice delivered).

Phase 0 (Specification) is complete and lives in the Forge specification workspace
(mirrored conceptually in `docs/`). The repository was previously empty, so this is the
first implementation slice.

## Implemented in this slice

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

- **Backend tests:** `cd backend && pytest` → 35 passed. Covers health, auth (success +
  failure paths), workspace RBAC, project CRUD, workspace isolation, pagination,
  optimistic-concurrency conflict, the error envelope, and the audit trail.
- **Lint:** `ruff check` → clean.
- **Migrations:** `alembic upgrade head` and `alembic downgrade base` both succeed on a
  fresh database (reversible).
- **Frontend:** `npm run build` → type-checks and builds (0 errors).
- **End-to-end:** live uvicorn + Vite dev server exercised via Playwright; screenshots in
  [`docs/screenshots/`](screenshots/) show register → Command Center → project creation →
  roadmap placeholder.

## Known limitations

- **SQLite in this environment.** The Docker daemon was unavailable during the build, so
  verification ran against SQLite. Postgres is the intended dev/prod database
  (`docker compose up -d db`); CI is configured to also run against Postgres. See
  ADR-0001 for the divergence-risk mitigations.
- **Auth is single-token.** No refresh tokens, rotation, or logout revocation yet;
  access tokens are short-lived. Password reset and email verification are out of scope
  for this slice.
- **No durable queue / workers yet.** That is Phase 2 (Durable Execution). Project status
  is a control-plane field only; runs and tasks do not exist yet.
- **Command-center placeholders.** Areas whose subsystems are not built (Agents, Tasks,
  Research, …) render an explicit "Planned — Phase N" page rather than fake data.
- **Rate limiting and idempotency keys** are specified (`22_API`) but not yet enforced;
  scaffolding for the error code exists.

## Next phase

**Phase 2 — Durable Execution**: run model, task model, state machine, durable queue,
worker lifecycle, leases/heartbeats, retries, cancellation, and checkpoints — building on
the `VersionedMixin` and audit foundations established here.
