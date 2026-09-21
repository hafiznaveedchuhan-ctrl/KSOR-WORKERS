"""Model routing: classify a query's complexity, then answer it with a
cheaper or a stronger model accordingly — the routing decision itself is
made by a separate, minimal classification call, not by the answering
agent guessing about its own difficulty."""

import asyncio

from agents import Agent, AgentsException, Runner
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

# The routing classifier itself always runs on the cheap model — classifying
# "is this simple or complex" is not itself a complex task.
MODEL_SIMPLE = MODEL  # "gpt-4o-mini"
MODEL_COMPLEX = "gpt-4o"


class RoutingDecision(BaseModel):
    query_type: str  # "simple" | "complex"
    reason: str


ROUTER_INSTRUCTIONS = (
    "Classify the following question as exactly one of:\n"
    "- \"simple\": a short, factual, single-step lookup with one clear "
    "answer.\n"
    "- \"complex\": requires multi-step reasoning, comparing multiple "
    "things, or synthesizing several facts together.\n"
    "Give a one-sentence reason for the classification."
)


async def run_router_agent(query: str) -> dict:
    # Same deterministic backstop as main.py's /ask (see ADR-003) —
    # checked before routing, since a decline needs no model selection.
    if is_refund_related(query):
        return {
            "query_type": "refund",
            "model_selected": None,
            "reason": "Deterministic refund-topic exclusion — routed to no model.",
            "answer": REFUND_DECLINE_MESSAGE,
        }

    router = Agent(
        name="Router",
        instructions=ROUTER_INSTRUCTIONS,
        model=MODEL,
        model_settings=ModelSettings(temperature=0),
        output_type=RoutingDecision,
    )
    routing_result = await Runner.run(router, query)
    decision: RoutingDecision = routing_result.final_output
    selected_model = MODEL_SIMPLE if decision.query_type == "simple" else MODEL_COMPLEX

    async with MCPServerStreamableHttp(
        name="KSOR",
        params={"url": MCP_URL},
        client_session_timeout_seconds=MCP_TIMEOUT_SECONDS,
    ) as ksor_server:
        agent = Agent(
            name="KSOR Worker (routed)",
            instructions=INSTRUCTIONS,
            model=selected_model,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
        )
        result = await Runner.run(agent, query)
        answer = result.final_output

    return {
        "query_type": decision.query_type,
        "model_selected": selected_model,
        "reason": decision.reason,
        "answer": answer,
    }


async def _cli() -> None:
    print("Router agent (complexity-based model selection). Type 'exit' to quit.\n")
    while True:
        query = input("You: ").strip()
        if query.lower() in {"exit", "quit"}:
            break
        try:
            result = await run_router_agent(query)
        except (MCPError, AgentsException) as exc:
            print(f"\n[error] KSOR MCP server unavailable: {exc}\n")
            continue
        print(f"\nQuery type:      {result['query_type']}")
        print(f"Model selected:  {result['model_selected']}")
        print(f"Reason:          {result['reason']}")
        print(f"Answer: {result['answer']}\n")


if __name__ == "__main__":
    asyncio.run(_cli())
