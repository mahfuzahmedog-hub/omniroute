# ADR-0006: Tool runtime — declarative contract, controlled environment, deny-by-default

- **Status:** Accepted
- **Date:** 2026-08-17
- **Phase:** 4 — Tool Runtime

## Context

Spec 06_TOOL_SYSTEM requires that every tool declares a fixed contract (name, schemas,
permissions, timeout, cost class, side effects, network requirements, audit policy,
recovery behavior), that "tools are denied by default" and projects grant scoped
permissions, that destructive/production operations "can require explicit human approval",
that every call "produces structured audit events … [and] secrets must never be stored in
raw tool logs", and that "command execution must occur inside controlled environments …
network egress and filesystem mounts are policy-controlled".

Two tensions had to be resolved, mirroring the Phase 3 agent decision (ADR-0005):

1. **Real vs. safe vs. honest.** Some capabilities (a headless browser, an external web
   search) need infrastructure/credentials that later phases provide. Full process/network
   isolation is the container sandbox of **Phase 5**. We must ship a genuinely useful,
   *safe* tool runtime now without faking capabilities or shipping unisolated host
   execution by default.
2. **Where enforcement lives.** Permission checks, validation, approval, timeouts, and
   audit could be scattered across each tool, or centralized.

## Decision

1. **Declarative contract.** A `ToolSpec` is a frozen dataclass carrying the full contract.
   New tools are just new values, inheriting the same permission, validation, approval, and
   audit machinery. A spec with `handler=None` is *declared but not runnable* (e.g.
   `browser.navigate`), failing loudly rather than faking output.

2. **One enforcement path.** `ToolRuntime.invoke` is the single choke point: resolve →
   authorize (deny-by-default project grant **and** agent least-privilege) → validate input
   schema → approval gate → execute in a controlled environment → validate output schema.
   Every outcome — including denials — is recorded as a durable `ToolInvocation` plus an
   `AuditEvent`, with argument metadata redacted and long values truncated so secrets and
   large blobs never land in the trail.

3. **Controlled environment seam.** `ExecutionEnvironment` abstracts the sandbox. The
   Phase-4 `LocalWorkspaceEnvironment` enforces the two controls achievable without
   containers: a **filesystem jail** (every path resolves under the project's workspace
   root; `..`, absolute paths, and escaping symlinks are refused) and a **deny-by-default
   egress policy** (a tool may only reach allow-listed hosts). The Phase-5 container sandbox
   will implement the same interface for full process isolation.

4. **Command execution is off by default outside local/dev.** The local environment does
   not fully isolate a spawned subprocess, so `env.run` is disabled in
   `staging`/`production`; command-spawning tools (`terminal`, `git`, `package`) fail loudly
   there until the container sandbox lands. This prevents unsafe host execution from ever
   shipping by default while keeping the tools genuinely runnable in development and tests.

5. **Agents use tools under least privilege.** An agent (Phase 3) receives a `ToolRuntime`
   in its context; `ctx.call_tool(...)` enforces that the capability is both in the agent's
   `allowed_tools` and granted to the project, and links the invocation to the run/task/agent.

## Consequences

- **Pros:** one governed execution path; tools are cheap to add and uniformly audited;
  deny-by-default + jail + egress give real, testable safety today; the Phase-5 sandbox
  only needs to implement `ExecutionEnvironment`, not a new runtime; nothing fake is
  presented as working.
- **Cons:** a few capabilities are inert until later phases (browser → Phase 15, search →
  Phase 6/9, package installs need an egress grant); the local environment does not isolate
  subprocesses, which is exactly why command execution is disabled outside local/dev.

## Alternatives considered

- **Let each tool enforce its own policy.** Less indirection, but guarantees drift: some
  tool eventually forgets to check permissions, redact secrets, or record an audit event.
- **Ship only once the container sandbox exists (Phase 5 first).** Safest-looking, but
  forfeits the contract, registry, permission model, approval gate, and audit scaffolding
  that Phases 5–7 build directly on, and blocks the agent↔tool integration.
- **A general shell tool.** Maximally flexible but an unbounded attack surface; we chose an
  allow-listed `terminal.run` (argv, `shell=False`) plus a curated offline `git` subset.
