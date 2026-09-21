"""Governance layer: detect and anonymize sensitive data in a query before
it ever reaches the KSOR MCP tools or gets logged in a search history."""

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


class PiiDetection(BaseModel):
    contains_sensitive_data: bool
    anonymized_query: str
    detected_types: list[str]  # e.g. ["NAME", "EMAIL"]


DETECTOR_INSTRUCTIONS = (
    "You detect personally identifiable or sensitive information in a "
    "user's question: full names, email addresses, phone numbers, "
    "financial data (card numbers, account numbers, amounts tied to a "
    "named account), and passwords or credentials.\n\n"
    "If you find any, replace each occurrence with a bracketed placeholder "
    "matching its type — [NAME], [EMAIL], [PHONE], [FINANCIAL], "
    "[PASSWORD] — and set contains_sensitive_data to true, listing every "
    "type found in detected_types. If you find nothing sensitive, return "
    "the query completely unchanged, contains_sensitive_data false, and an "
    "empty detected_types list. Never remove or alter anything that isn't "
    "sensitive — only replace the sensitive spans."
)


async def run_policy_agent(query: str) -> dict:
    detector = Agent(
        name="PII Detector",
        instructions=DETECTOR_INSTRUCTIONS,
        model=MODEL,
        model_settings=ModelSettings(temperature=0),
        output_type=PiiDetection,
    )
    detection_result = await Runner.run(detector, query)
    detection: PiiDetection = detection_result.final_output

    # Same deterministic backstop as main.py's /ask (see ADR-003) — checked
    # on the ANONYMIZED query, since that's what would otherwise be sent on
    # to the KSOR-scoped agent below.
    if is_refund_related(detection.anonymized_query):
        return {
            "original_query": query,
            "anonymized_query": detection.anonymized_query,
            "detected_types": detection.detected_types,
            "answer": REFUND_DECLINE_MESSAGE,
        }

    async with MCPServerStreamableHttp(
        name="KSOR",
        params={"url": MCP_URL},
        client_session_timeout_seconds=MCP_TIMEOUT_SECONDS,
    ) as ksor_server:
        agent = Agent(
            name="KSOR Worker (policy-filtered)",
            instructions=INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
        )
        result = await Runner.run(agent, detection.anonymized_query)
        answer = result.final_output

    return {
        "original_query": query,
        "anonymized_query": detection.anonymized_query,
        "detected_types": detection.detected_types,
        "answer": answer,
    }


async def _cli() -> None:
    print("Policy agent (PII detection + anonymized answer). Type 'exit' to quit.\n")
    while True:
        query = input("You: ").strip()
        if query.lower() in {"exit", "quit"}:
            break
        try:
            result = await run_policy_agent(query)
        except (MCPError, AgentsException) as exc:
            print(f"\n[error] KSOR MCP server unavailable: {exc}\n")
            continue
        print(f"\nOriginal query:   {result['original_query']}")
        print(f"Anonymized query: {result['anonymized_query']}")
        if result["detected_types"]:
            print(f"Detected:         {result['detected_types']}")
        print(f"Answer: {result['answer']}\n")


if __name__ == "__main__":
    asyncio.run(_cli())
