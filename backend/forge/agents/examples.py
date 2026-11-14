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


def _fs_roundtrip(ctx: AgentContext) -> dict:
    """Write a file and read it back — through the tool runtime, under least privilege."""
    path = ctx.inputs["path"]
    content = ctx.inputs["content"]
    ctx.call_tool("fs.write", {"path": path, "content": content})
    read = ctx.call_tool("fs.read", {"path": path})
    return {"path": path, "roundtrip_ok": read["content"] == content}


def _verify_roundtrip(ctx: AgentContext, outputs: dict) -> list[VerificationCheck]:
    ok = outputs.get("roundtrip_ok") is True
    return [VerificationCheck("file_roundtrip", ok, "" if ok else "content mismatch")]


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

# An example agent that actually uses tools, demonstrating the Phase 3 ↔ Phase 4 seam:
# it may only touch the "filesystem" capability, which must also be granted to the project.
fs_roundtrip_agent = Agent(
    key="example.fs_roundtrip",
    role="Workspace Scribe",
    objective="Write a file into the project workspace and read it back to verify it.",
    input_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    },
    output_schema={
        "type": "object",
        "properties": {"path": {"type": "string"}, "roundtrip_ok": {"type": "boolean"}},
        "required": ["path", "roundtrip_ok"],
    },
    allowed_tools=frozenset({"filesystem"}),
    execute=_fs_roundtrip,
    verify=_verify_roundtrip,
)

EXAMPLE_AGENTS = [wordcount_agent, sum_agent, fs_roundtrip_agent]
