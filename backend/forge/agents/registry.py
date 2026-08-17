"""Agent registry and the initial agent ecosystem.

The registry is the catalog of known agents. The initial roster from spec 04_AGENT_SYSTEM
is registered here as **declared contracts** (``execute=None``) — their identities, roles,
permissions, budgets, and model policies are real and queryable, but their executors are
supplied once the model runtime (Phases 10/13) exists. Executable *example* agents live in
:mod:`forge.agents.examples` and are registered too, so the framework is exercised
end-to-end without pretending the model-backed roster already works.
"""

from __future__ import annotations

from forge.agents.contract import Agent, AgentBudget


class AgentRegistry:
    """A catalog of agents keyed by their unique ``key``."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> Agent:
        if agent.key in self._agents:
            raise ValueError(f"Agent '{agent.key}' is already registered")
        self._agents[agent.key] = agent
        return agent

    def get(self, key: str) -> Agent | None:
        return self._agents.get(key)

    def all(self) -> list[Agent]:
        return [self._agents[k] for k in sorted(self._agents)]

    def runnable_keys(self) -> list[str]:
        return sorted(k for k, a in self._agents.items() if a.runnable)


# The initial roster: role + objective + least-privilege tools + model class.
# execute=None → declared contract, not yet runnable (awaits the model runtime).
_ROSTER: list[tuple[str, str, str, frozenset[str], str]] = [
    ("commander", "Commander",
     "Own the project run end-to-end and delegate to specialists.",
     frozenset(), "reasoning"),
    ("researcher", "Researcher",
     "Investigate the ecosystem and produce an evidence-backed research package.",
     frozenset({"http", "search"}), "reasoning"),
    ("product_manager", "Product Manager",
     "Turn goals into requirements and acceptance criteria.",
     frozenset(), "reasoning"),
    ("planner", "Planner",
     "Decompose validated requirements into a dependency-aware task graph.",
     frozenset(), "reasoning"),
    ("architect", "Architect",
     "Produce architecture and decision records from validated findings.",
     frozenset(), "reasoning"),
    ("database_engineer", "Database Engineer",
     "Design and migrate the data model.",
     frozenset({"filesystem", "database"}), "coding"),
    ("backend_engineer", "Backend Engineer",
     "Implement backend services and APIs.",
     frozenset({"filesystem", "terminal", "git"}), "coding"),
    ("frontend_engineer", "Frontend Engineer",
     "Implement the user interface.",
     frozenset({"filesystem", "terminal", "git"}), "coding"),
    ("ai_engineer", "AI Engineer",
     "Integrate AI/model features.",
     frozenset({"filesystem", "terminal"}), "coding"),
    ("devops_engineer", "DevOps Engineer",
     "Provision environments and pipelines.",
     frozenset({"terminal", "docker"}), "coding"),
    ("test_engineer", "Test Engineer",
     "Write and run automated tests.",
     frozenset({"filesystem", "terminal"}), "coding"),
    ("security_engineer", "Security Engineer",
     "Find and block insecure patterns before release.",
     frozenset({"filesystem", "terminal"}), "reasoning"),
    ("performance_engineer", "Performance Engineer",
     "Identify and fix performance regressions.",
     frozenset({"terminal"}), "reasoning"),
    ("browser_qa", "Browser QA",
     "Validate the running app through a controlled browser.",
     frozenset({"browser"}), "vision"),
    ("code_reviewer", "Code Reviewer",
     "Review changes against specs and acceptance criteria.",
     frozenset({"filesystem", "git"}), "reasoning"),
    ("debugger", "Debugger",
     "Diagnose failures and propose fixes.",
     frozenset({"filesystem", "terminal", "git"}), "reasoning"),
    ("release_engineer", "Release Engineer",
     "Run release verification and deploy under policy.",
     frozenset({"terminal", "deployment"}), "coding"),
]


def _register_roster(registry: AgentRegistry) -> None:
    for key, role, objective, tools, model_class in _ROSTER:
        registry.register(
            Agent(
                key=key,
                role=role,
                objective=objective,
                allowed_tools=tools,
                model_policy={"class": model_class},
                budget=AgentBudget(max_usd=5.0, max_tokens=200_000, max_seconds=1800),
                escalation_target="commander" if key != "commander" else None,
            )
        )


def build_default_registry() -> AgentRegistry:
    """Construct the process-wide registry: roster specs + executable examples."""
    registry = AgentRegistry()
    _register_roster(registry)

    # Registering examples here (lazily imported to avoid a circular import) gives the
    # framework at least a few genuinely runnable agents.
    from forge.agents import examples

    for agent in examples.EXAMPLE_AGENTS:
        registry.register(agent)
    return registry


registry = build_default_registry()
