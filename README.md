# ⚒️ Forge

Forge is a production-grade **autonomous software engineering platform**: it takes a
high-level software goal and turns it into researched, architected, implemented,
tested, reviewed, secured, and deployable software with persistent project memory and
self-healing execution.

This repository (`omniroute`) is the implementation of Forge. It is built
**specification-first**: the authoritative product and engineering specs live alongside
the code in [`docs/`](docs/) and are mirrored from the Forge specification workspace.

> **Status:** Phase 4 — Tool Runtime. See [`docs/STATUS.md`](docs/STATUS.md) for the
> current build phase, what is implemented, and the known limitations.

---

## Repository layout

```
omniroute/
├── backend/            FastAPI control-plane API + durable data model (Python 3.11)
│   ├── forge/          Application package (config, db, models, api, core, services,
│   │                   orchestration, agents, tools)
│   ├── migrations/     Alembic versioned migrations
│   └── tests/          pytest suite (executable contracts)
├── frontend/           React + TypeScript + Vite command-center UI shell
├── docs/               Specs, ADRs, and build status
│   └── adr/            Architecture Decision Records
├── docker-compose.yml  Local Postgres for development
├── Makefile            Common developer tasks
└── .github/workflows/  CI (lint + tests)
```

The architecture follows the **control-plane / data-plane** split described in
`docs/adr/`: this codebase is the *control plane* (projects, tasks, agents, policy,
state). The data plane (sandboxes that execute agent code and tools) is introduced in
later phases per `BUILD_ORDER`.

---

## Quick start (backend)

Requirements: Python 3.11+.

```bash
# 1. Install dependencies (editable, with dev extras)
make backend-install

# 2. Copy environment template and set a real secret
cp backend/.env.example backend/.env
#   Edit FORGE_SECRET_KEY to a long random value.

# 3. Run the database migrations
make migrate            # uses FORGE_DATABASE_URL (defaults to local SQLite)

# 4. Run the API
make backend-run        # serves http://localhost:8000, docs at /docs
```

Open http://localhost:8000/docs for the interactive OpenAPI documentation, or
http://localhost:8000/api/v1/health for a health probe.

### Using Postgres locally

```bash
docker compose up -d db          # starts Postgres on localhost:5432
export FORGE_DATABASE_URL=postgresql+psycopg://forge:forge@localhost:5432/forge
make migrate
make backend-run
```

## Quick start (frontend)

Requirements: Node 20+.

```bash
make frontend-install
make frontend-dev        # serves http://localhost:5173, proxies /api to :8000
```

---

## Testing

```bash
make test                # backend pytest suite
make frontend-build      # type-checks and builds the UI
```

Forge treats **tests as executable contracts** (see `docs/24_TESTING` in the spec set).
The Phase 1 suite covers the health probe, authentication, workspace RBAC, project CRUD,
the standardized error envelope, pagination, and optimistic-concurrency versioning.

---

## Engineering discipline

Every non-trivial change follows the mandatory lifecycle:

```
RESEARCH → VALIDATE → ARCHITECT → IMPLEMENT → TEST → REVIEW → IMPROVE
```

Cross-cutting decisions are recorded as ADRs in [`docs/adr/`](docs/adr/). Core
invariants (durable state, auditability, verified completion, least privilege,
recoverability, replaceable models, resumability) are defined in the master spec and
must not be silently violated by an implementation.
