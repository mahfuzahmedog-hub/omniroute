"""Output verification for agents.

The completion rule from spec 04_AGENT_SYSTEM: an agent cannot mark a task complete
unless the required outputs exist and the verification contract passes. Verification here
always includes an output JSON-Schema check, plus any custom checks the agent declares.
"""

from __future__ import annotations

from dataclasses import dataclass

import jsonschema

from forge.agents.context import AgentContext
from forge.agents.contract import Agent, VerificationCheck


class SchemaValidationError(Exception):
    """Raised when a JSON instance does not conform to its schema."""


def validate_schema(instance: dict, schema: dict) -> None:
    try:
        jsonschema.validate(instance=instance, schema=schema)
    except jsonschema.ValidationError as exc:
        # exc.message is concise; the full exc is verbose and noisy for audit logs.
        raise SchemaValidationError(exc.message) from None


@dataclass
class VerificationResult:
    passed: bool
    checks: list[VerificationCheck]

    def to_dict(self) -> dict:
        return {"passed": self.passed, "checks": [c.to_dict() for c in self.checks]}


def run_verification(agent: Agent, ctx: AgentContext, outputs: dict) -> VerificationResult:
    """Run the automatic output-schema check plus the agent's custom verifier."""
    checks: list[VerificationCheck] = []
    try:
        validate_schema(outputs, agent.output_schema)
        checks.append(VerificationCheck("output_schema", True))
    except SchemaValidationError as exc:
        checks.append(VerificationCheck("output_schema", False, str(exc)))

    if agent.verify is not None:
        checks.extend(agent.verify(ctx, outputs))

    return VerificationResult(passed=all(c.passed for c in checks), checks=checks)
