# ADR-0005: Agents as a declarative framework over the task queue

- **Status:** Accepted
- **Date:** 2026-08-17
- **Phase:** 3 — Agent Runtime

## Context

Spec 04_AGENT_SYSTEM insists that "agents should be implemented through a reusable
framework rather than as hard-coded one-off workflows", that each agent declares a fixed
contract (identity, schemas, tools, permissions, model policy, budget, timeout, retry,
verification, escalation), and that "an agent cannot mark a task complete unless required
outputs exist and the verification contract passes". Agents also need somewhere to *run*
that is durable and recoverable — which Phase 2 already provides.

Two tensions had to be resolved:

1. **Real vs. honest.** Most roster agents (Researcher, Architect, …) genuinely need a
   language model, which does not exist until the model runtime (Phases 10/13). We must
   not ship fake agents that pretend to produce model output.
2. **Where agents execute.** Agents could get a bespoke execution loop, or reuse the
   durable task engine.

## Decision

1. **Declarative contract.** An `Agent` is a frozen dataclass carrying the full contract.
   New agents — including future dynamic ones — are just new values, so they inherit the
   same validation, permission, budget, and verification machinery for free.

2. **Agents run as tasks.** An agent executes as a task whose `kind` equals the agent's
   `key`. `build_agent_handler` wraps an agent into a Phase 2 worker handler that assembles
   a focused context, validates inputs, records a durable `AgentExecution`, runs the
   executor under its budget, verifies outputs, and only then reports success. Failures
   raise, so the existing retry / dead-letter / lease machinery applies unchanged — no
   second execution engine.

3. **Spec-only roster + executable examples.** The initial roster is registered as
   **declared contracts with `execute=None`**: real identities/roles/permissions/budgets,
   queryable via the catalog API, but not yet runnable. Invoking one fails loudly
   ("no executor yet"). A couple of genuinely deterministic **example agents** are
   registered as runnable so the framework is exercised end-to-end. This mirrors the UI's
   honest "Planned — Phase N" placeholders: nothing fake is presented as working.

4. **Completion = outputs + verification.** Verification always includes an output
   JSON-Schema check plus any custom checks the agent declares; a failing contract fails
   the task.

## Consequences

- **Pros:** one execution/recovery engine; agents are cheap to add and uniformly governed;
  the roster documents the target ecosystem in code today; the model runtime later only
  needs to supply executors, not a new runtime.
- **Cons:** the roster is inert until the model runtime lands; representing agents as task
  kinds means agent identity currently lives in the task's `kind` string (a dedicated
  agent-assignment column can be added if needed).

## Alternatives considered

- **A bespoke agent execution loop** separate from the task engine. More direct control,
  but duplicates durability, retries, leases, and cancellation that Phase 2 already solves.
- **Only ship agents once the model runtime exists.** Honest, but forfeits the framework,
  catalog, verification, and budget scaffolding that later phases depend on.
