# ADR-0002: Durable state and optimistic concurrency

- **Status:** Accepted
- **Date:** 2026-08-17
- **Phase:** 1 — Foundation

## Context

Two master-spec invariants shape how Forge stores state:

> Every task has durable state. … Persist task transitions and version them to prevent
> stale workers from overwriting newer state.

Forge will eventually run many workers against the same rows (a scheduler hands tasks to
a horizontally scalable worker fleet). Two dangers follow: (1) important state living
only in process memory is lost on restart, and (2) a slow worker holding an old copy of
a row can overwrite a newer update — the classic *lost update* problem.

## Decision

1. **Durable-first state.** Core entities are relational rows, not in-memory objects.
   Even in Phase 1, project lifecycle status and the audit trail are persisted.

2. **Optimistic concurrency via a `version` column.** A `VersionedMixin` adds an integer
   `version` and wires SQLAlchemy's `version_id_col`. Every UPDATE increments `version`
   and adds `version = :old` to the WHERE clause. A stale write therefore matches zero
   rows and raises `StaleDataError`, which the API maps to `409 Conflict`.

3. **Explicit, optional client concurrency control.** Mutating endpoints accept an
   optional `expected_version`. When supplied and stale, the request is rejected with
   `409` *before* any write — letting clients implement compare-and-set safely.

4. **Atomic audit trail.** `AuditEvent` rows are written in the *same transaction* as the
   state change they describe, so an action and its audit record commit together or not
   at all.

## Intuition (toy example)

Two workers read project `P` at `version = 4`.

```
Worker A: set status=active   (expects v4) → UPDATE ... WHERE id=P AND version=4 → v5 ✓
Worker B: set status=paused    (expects v4) → UPDATE ... WHERE id=P AND version=4 → 0 rows → 409
```

Without the version guard, B would silently overwrite A. With it, B is told to re-read
and retry.

## Consequences

- Clients must handle `409` on contended writes (documented in the API).
- The counter is cheap and database-agnostic (works identically on SQLite and Postgres).
- Later phases extend the same mechanism to the `runs`/`tasks` tables, where it matters
  most, without inventing a second pattern.

## Alternatives considered

- **Pessimistic locking (`SELECT … FOR UPDATE`).** Simpler mental model but holds locks
  across potentially long agent operations and does not translate to SQLite.
- **Last-write-wins.** Trivial, but directly violates the master-spec invariant.
