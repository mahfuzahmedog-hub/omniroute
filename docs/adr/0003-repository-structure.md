# ADR-0003: Repository structure

- **Status:** Accepted
- **Date:** 2026-08-17
- **Phase:** 1 — Foundation

## Context

Forge spans many subsystems (API, orchestration, agents, tools, sandbox, memory, …). We
need a layout that keeps the **control plane** and **UI** cleanly separated, supports
independent testing of subsystems (Build Philosophy #2), and leaves obvious homes for
the subsystems introduced in later phases.

## Decision

A single repository (monorepo) with top-level boundaries:

```
backend/    Python control-plane API + durable data model
frontend/   React command-center UI
docs/       Specs, ADRs, build status, QA evidence
```

Within `backend/forge/`, code is grouped by architectural role rather than by feature,
so each spec subsystem maps to a predictable module:

```
forge/
  config.py     configuration (pydantic-settings)
  logging.py    structured logging + correlation context
  db/           engine, session, portable column types
  models/       durable SQLAlchemy entities
  schemas/      Pydantic request/response contracts
  core/         cross-cutting: security, errors, deps, pagination, middleware
  services/     domain services (e.g. audit trail)
  api/routes/   HTTP routes grouped by domain
migrations/     Alembic versioned migrations
tests/          pytest suite
```

New subsystems land as new packages (e.g. `forge/orchestration/`, `forge/agents/`,
`forge/tools/`) alongside the existing ones.

## Consequences

- One clone, one PR spans coordinated backend+frontend+docs changes.
- Grouping by role keeps the security choke points (`core/deps.py`, `core/security.py`)
  centralized and easy to audit.
- If a subsystem later needs to scale as a separate deployable (e.g. the worker fleet),
  it can be extracted; the role-based layout makes the seams clear.

## Alternatives considered

- **Separate repos per subsystem.** Better isolation but heavy coordination cost this
  early, when interfaces are still moving.
- **Feature-based backend layout.** Co-locates everything for one feature, but scatters
  the security and persistence primitives that must stay centralized.
