"""Executable example agents.

These are small, fully deterministic agents (no model calls) whose only purpose is to
exercise the agent framework end-to-end: schema-validated I/O, context assembly, budget
accounting, verification contracts, and durable execution records. They are honest, real
agents — not stand-ins that fake model output.
"""

from __future__ import annotations

from forge.agents.context import AgentContext
from forge.agents.contract import Agent, AgentBudget, VerificationCheck


def _wordcount(ctx: AgentContext) -> dict:
    text: str = ctx.inputs["text"]
    ctx.record_usage(tokens=len(text.split()))  # pretend token accounting
    return {"words": len(text.split()), "chars": len(text)}


def _verify_wordcount(ctx: AgentContext, outputs: dict) -> list[VerificationCheck]:
    text: str = ctx.inputs["text"]
    ok = outputs.get("words") == len(text.split())
    return [VerificationCheck("word_count_matches_input", ok, "" if ok else "miscount")]


def _sum(ctx: AgentContext) -> dict:
    numbers = ctx.inputs["numbers"]
    return {"sum": sum(numbers)}


wordcount_agent = Agent(
    key="example.wordcount",
    role="Text Analyzer",
    objective="Count the words and characters in a piece of text.",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    output_schema={
        "type": "object",
        "properties": {"words": {"type": "integer"}, "chars": {"type": "integer"}},
        "required": ["words", "chars"],
    },
    budget=AgentBudget(max_tokens=10_000, max_usd=0.01),
    execute=_wordcount,
    verify=_verify_wordcount,
)

sum_agent = Agent(
    key="example.sum",
    role="Calculator",
    objective="Sum a list of numbers.",
    input_schema={
        "type": "object",
        "properties": {"numbers": {"type": "array", "items": {"type": "number"}}},
        "required": ["numbers"],
    },
    output_schema={
        "type": "object",
        "properties": {"sum": {"type": "number"}},
        "required": ["sum"],
    },
    execute=_sum,
)

EXAMPLE_AGENTS = [wordcount_agent, sum_agent]
