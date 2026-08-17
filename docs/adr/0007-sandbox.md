# ADR-0007: Sandbox as a backend-agnostic lifecycle over the execution environment

- **Status:** Accepted
- **Date:** 2026-08-17
- **Phase:** 5 — Sandbox

## Context

Spec 07_SANDBOX requires "isolated, reproducible environments where agents can safely build
and test software", with a lifecycle (provision → initialize → execute → checkpoint →
reset/destroy), project isolation, resource controls, and reproducibility metadata. Phase 4
already introduced the `ExecutionEnvironment` seam and a path-jailed `LocalWorkspaceEnvironment`.

Full process/network/resource isolation needs a container runtime. **In this build
environment the Docker daemon is unavailable**, so a container-backed sandbox cannot be
executed or verified here. The project's rules forbid claiming completion without test
evidence and forbid presenting fake implementations as working, so we must not ship a large
untested container orchestration as if it were done.

## Decision

1. **A backend-agnostic `Sandbox` interface** owns the lifecycle and exposes the Phase 4
   `ExecutionEnvironment`. The tool runtime obtains its environment from a `SandboxProvider`,
   so it never knows which backend hosts it.

2. **`LocalSandbox` is real and fully tested.** It wraps `LocalWorkspaceEnvironment` and adds
   provision/initialize, tar-based **snapshot/reset** (checkpoint + rollback), destroy, and
   reproducibility metadata. This is the default development sandbox and the environment
   tools run in today.

3. **`DockerSandbox` is honest, not faked.** It detects daemon availability; when none is
   reachable it raises `SandboxUnavailable` rather than pretending to isolate anything
   (the same posture as the declared-only browser tool and the spec-only agent roster). Its
   docstring records the intended Docker CLI lifecycle so the implementation is a
   straightforward fill-in once a daemon is available.

4. **`ResourceLimits` are declared and recorded now, enforced by the container backend
   later.** The local backend can only enforce wall-clock time (per-command timeouts); the
   other limits are captured for reproducibility until a container runs the workload.

## Consequences

- **Pros:** the sandbox lifecycle, provider seam, snapshot/reset, and reproducibility are
  real and tested today; Phase 4 tools now run "inside a sandbox" abstraction; the container
  backend has a precise, isolated place to land with zero churn elsewhere.
- **Cons / deferred (blocked on a Docker daemon):** container isolation, OS-level
  resource/network enforcement, the secret broker's injection into isolated processes, and
  package-cache/database/browser services inside the sandbox are **not** delivered in this
  slice. They are gated behind the daemon and clearly marked in `docs/STATUS.md`.

## Alternatives considered

- **Implement the full Docker backend now anyway.** Rejected: it cannot be tested without a
  daemon, so it would violate "no unverified completion" and risk shipping broken
  orchestration.
- **Use Linux namespaces (`unshare`) for isolation.** `unshare` exists in this environment,
  but nesting user/network namespaces reliably inside an already-sandboxed CI container is
  fragile and still unverifiable for the network/resource controls the spec wants; the
  container runtime is the specified, portable mechanism.
- **Block Phase 5 entirely until Docker is provisioned.** Rejected: the lifecycle,
  snapshot/reset, and provider seam are valuable and verifiable now, and unblock the tool
  runtime's "runs inside a sandbox" contract.
