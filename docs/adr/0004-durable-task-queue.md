# ADR-0004: Durable task queue on the primary database

- **Status:** Accepted
- **Date:** 2026-08-17
- **Phase:** 2 — Durable Execution

## Context

Phase 2 needs a queue that hands runnable tasks to workers. The architecture spec is
explicit that "workers consume work from durable queues rather than relying on in-process
background tasks", that "long-running jobs must not depend on one API process remaining
alive", and that runs "must survive API restarts and worker crashes". We also want the
platform to run with the fewest moving parts in development (the master prompt: "prefer
boring, reliable infrastructure over unnecessary complexity") while staying correct under
multiple concurrent workers.

A dedicated broker (Redis, RabbitMQ, SQS, Celery, etc.) is the obvious option, but it adds
a second stateful system to operate, and — crucially — a broker separate from the database
reintroduces the dual-write problem: a task could be committed to the DB but lost from the
broker, or vice versa.

## Decision

Use the **primary relational database as the durable queue**. The `tasks` table *is* the
queue; there is no separate broker.

- **Claiming** a task is an atomic, conditional UPDATE guarded by the task's `version`
  column (optimistic concurrency, ADR-0002). A worker reads a candidate `ready` task and
  writes `status=running, lease_owner, lease_expires_at, attempts+=1`. If another worker
  claimed it first, the UPDATE matches zero rows (`StaleDataError`) and the worker moves to
  the next candidate. Two workers therefore cannot both win the same task.
- **Leases** (`lease_owner`, `lease_expires_at`) bound how long a worker may hold a task.
  A reaper returns tasks whose lease expired back to `ready`, which is how a crashed
  worker's in-flight work is recovered.
- **Backoff** is expressed as a future `available_at`; a task is only claimable once
  `available_at <= now`, giving exponential retry backoff without any timer service.

This keeps task state and queue state in one place, so they commit together and can never
diverge.

## Consequences

- **Pros:** one system to operate; exactly-once-ish claiming via the DB's own transactional
  guarantees; trivial durability and crash recovery; identical behavior on SQLite (tests)
  and PostgreSQL (prod).
- **Cons:** workers poll rather than receive push notifications (mitigated by short sleeps
  and, later, `LISTEN/NOTIFY`); very high task throughput will eventually pressure the
  database. Postgres `SELECT ... FOR UPDATE SKIP LOCKED` can replace the optimistic-claim
  loop for efficiency later without changing the contract.

## Alternatives considered

- **Celery + Redis/RabbitMQ.** Battle-tested and push-based, but adds a broker to operate,
  weakens the durability story (dual writes), and is harder to run identically in tests.
- **Cloud queue (SQS).** Offloads ops but couples the core engine to a provider, conflicting
  with the "keep infrastructure replaceable / boring" principle at this stage.
