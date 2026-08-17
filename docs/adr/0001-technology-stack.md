# ADR-0001: Technology stack for the Forge control plane

- **Status:** Proposed (awaiting Product Owner confirmation — a major technology choice)
- **Date:** 2026-08-17
- **Phase:** 1 — Foundation

## Context

Forge is a large, long-lived autonomous software engineering platform. The master
spec and subsystem specs impose concrete constraints on the foundation:

- **Durable, relational core state** with versioned task transitions (`23_DATABASE`,
  `05_ORCHESTRATION`).
- **Schema-validated, versioned APIs** with generated OpenAPI and stable error codes
  (`22_API`).
- **Control-plane / data-plane split**, event-driven, horizontally scalable workers
  (`03_ARCHITECTURE`).
- **Replaceable model providers** and a strong AI/agent ecosystem (`13_MODEL_ROUTER`,
  `04_AGENT_SYSTEM`).
- **A rich "command center" UI** with many live views (`21_UI`).

We must choose a stack we can build, test, and operate reliably, favouring "boring,
reliable infrastructure over unnecessary complexity" (master build prompt).

## Decision

| Concern | Choice | Why |
| --- | --- | --- |
| API framework | **FastAPI (Python 3.11)** | First-class Pydantic schema validation and auto-generated OpenAPI satisfy `22_API` directly; async-ready. |
| Data / ORM | **SQLAlchemy 2.0 + Alembic** | Relational constraints for core state; Alembic gives versioned, reversible migrations (`23_DATABASE`). |
| Database | **PostgreSQL** (prod/dev), **SQLite** (tests/local) | Postgres for transactional integrity and JSONB; SQLite keeps tests fast and zero-config. Portability handled by a custom `GUID` type. |
| Auth | **JWT (HS256) + bcrypt** | Standard, stateless bearer auth; algorithm/TTL are configurable so signing stays replaceable. |
| Config | **pydantic-settings** | 12-factor, validated-at-startup configuration; fails fast on unsafe production config. |
| Frontend | **React + TypeScript + Vite + Tailwind** | Fast, typed, component-driven command center; large ecosystem for the many live views. |
| Tests | **pytest + httpx** (backend), **tsc/vite build** (frontend) | Tests as executable contracts (`24_TESTING`). |

Python is chosen for the backend deliberately: the agent/model/research subsystems that
dominate later phases have their richest, best-supported SDKs in Python, so keeping the
control plane and the agent runtime in one language reduces friction.

## Alternatives considered

- **TypeScript/Node end-to-end (e.g. NestJS).** One language across the stack, but
  weaker first-party AI/ML tooling for the later engineering/research phases.
- **Go control plane.** Excellent concurrency and single-binary ops, but a heavier
  authoring cost for schema/ORM ergonomics and a worse fit for the Python-centric agent
  ecosystem.

## Consequences

- SQLite-for-tests vs Postgres-for-prod introduces a small divergence risk (e.g. native
  enum types, JSONB operators). Mitigations: a portable `GUID` type, `native_enum=False`
  enums, `JSON` columns, and CI that can additionally run the suite against Postgres.
- The control plane is synchronous FastAPI today; the durable queue and worker fleet
  (`Phase 2`) will introduce async execution without changing the API contract.

## Change control

Superseding this stack requires a new ADR and a migration plan, per the master spec's
change-control rule.
