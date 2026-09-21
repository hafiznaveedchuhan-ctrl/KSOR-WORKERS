"""Output evaluation: answer a query via KSOR, then judge whether the
answer is actually supported by the source chunks that were retrieved for
it — not by re-running search separately, but by reading the exact tool
output the answering agent saw (see `_extract_search_hits`)."""

import asyncio
import json

from agents import Agent, AgentsException, Runner, ToolCallOutputItem
from agents.mcp import MCPServerStreamableHttp
from agents.model_settings import ModelSettings
from mcp.shared.exceptions import MCPError
from pydantic import BaseModel

from ksor_worker.common import (
    INSTRUCTIONS,
    MCP_TIMEOUT_SECONDS,
    MCP_URL,
    MODEL,
    REFUND_DECLINE_MESSAGE,
    is_refund_related,
)


class EvalVerdict(BaseModel):
    verdict: str  # "GROUNDED" | "PARTIALLY_GROUNDED" | "HALLUCINATED"
    matched_citations: list[str]
    explanation: str


JUDGE_INSTRUCTIONS = (
    "You are a strict fact-checker. You are given a QUESTION, an ANSWER "
    "that was supposedly generated using the SOURCE CHUNKS below it, and "
    "those source chunks themselves (each labeled with its document "
    "slug).\n\n"
    "First check: is the ANSWER an honest abstention — it says the topic "
    "isn't covered, is outside scope, or it doesn't know, WITHOUT asserting "
    "any other fact? That is \"GROUNDED\" behavior, never "
    "\"HALLUCINATED\" — declining when there is no supporting evidence is "
    "the correct outcome, not a fabrication. Only mark an abstention "
    "otherwise if it also sneaks in an unsupported claim alongside the "
    "refusal.\n\n"
    "Otherwise, check whether every factual claim in the ANSWER is "
    "actually supported by the SOURCE CHUNKS. Return:\n"
    "- verdict: \"GROUNDED\" if every claim is supported by the source "
    "chunks (or the answer is a clean abstention, per above), "
    "\"PARTIALLY_GROUNDED\" if some claims are supported but others are "
    "not verifiable from the source chunks, \"HALLUCINATED\" if the answer "
    "contains claims that contradict or have no basis anywhere in the "
    "source chunks.\n"
    "- matched_citations: the slugs of the source chunks that actually "
    "support the answer. Empty if none do (including for a clean "
    "abstention).\n"
    "- explanation: one or two sentences on why."
)


def _extract_search_hits(result) -> str:
    """Pull the raw KSOR `search` tool output(s) actually used to produce
    this answer, from the run's own item trace — not a second, possibly
    different search — so the judge sees exactly what the answering agent
    saw. Returns a plain-text block for the judge's prompt."""
    chunks: list[str] = []
    for item in result.new_items:
        if not isinstance(item, ToolCallOutputItem):
            continue
        output = item.output
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except (json.JSONDecodeError, ValueError):
                chunks.append(output)
                continue
        if isinstance(output, dict) and "hits" in output:
            for hit in output["hits"]:
                chunks.append(f"[{hit.get('slug', '?')}] {hit.get('content', '')}")
        else:
            chunks.append(json.dumps(output))
    return "\n\n".join(chunks) if chunks else "(no search results were retrieved)"


async def run_eval_agent(query: str) -> tuple[str, EvalVerdict]:
    # Same deterministic backstop as main.py's /ask — this agent answers
    # using the identical INSTRUCTIONS (including the prompt-only refund
    # carve-out already proven unreliable on its own, see ADR-003). No
    # search happens for a short-circuited decline, so there is nothing
    # for the judge to evaluate — the decline itself is definitionally
    # correct, so it's returned as GROUNDED without spending a judge call.
    if is_refund_related(query):
        return REFUND_DECLINE_MESSAGE, EvalVerdict(
            verdict="GROUNDED",
            matched_citations=[],
            explanation="Deterministic refund-topic exclusion — correctly declined before any search.",
        )

    async with MCPServerStreamableHttp(
        name="KSOR",
        params={"url": MCP_URL},
        client_session_timeout_seconds=MCP_TIMEOUT_SECONDS,
    ) as ksor_server:
        answer_agent = Agent(
            name="KSOR Worker (under evaluation)",
            instructions=INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
        )
        result = await Runner.run(answer_agent, query)
        answer = result.final_output
        source_chunks = _extract_search_hits(result)

    judge = Agent(
        name="Groundedness Judge",
        instructions=JUDGE_INSTRUCTIONS,
        model=MODEL,
        model_settings=ModelSettings(temperature=0),
        output_type=EvalVerdict,
    )
    judge_input = (
        f"QUESTION:\n{query}\n\nANSWER:\n{answer}\n\nSOURCE CHUNKS:\n{source_chunks}"
    )
    judge_result = await Runner.run(judge, judge_input)
    verdict: EvalVerdict = judge_result.final_output

    return answer, verdict


async def _cli() -> None:
    print("Eval agent (grounded answer + groundedness verdict). Type 'exit' to quit.\n")
    while True:
        query = input("You: ").strip()
        if query.lower() in {"exit", "quit"}:
            break
        try:
            answer, verdict = await run_eval_agent(query)
        except (MCPError, AgentsException) as exc:
            print(f"\n[error] KSOR MCP server unavailable: {exc}\n")
            continue
        print(f"\nAnswer: {answer}")
        print(f"Citations matched: {verdict.matched_citations}")
        print(f"Verdict: {verdict.verdict}")
        print(f"Why: {verdict.explanation}\n")


if __name__ == "__main__":
    asyncio.run(_cli())
