from agents import Agent, Runner, SQLiteSession
from agents.mcp import MCPServerStreamableHttp
from agents.model_settings import ModelSettings

from ksor_worker.common import MCP_TIMEOUT_SECONDS, MCP_URL, MODEL

# Runtime state, not source — see .gitignore.
REFUND_SESSIONS_DB = "refund_sessions.db"

# The mirror image of worker.py's carve-out: this agent answers ONLY
# refund/return/cancellation questions, and declines everything else the
# KSOR covers too (product hunting, reviews, sourcing, listings) — so the
# two agents' domains never overlap in what they'll actually answer.
INSTRUCTIONS = (
    "You are the refund and returns assistant for Ibrahim Digital "
    "Solutions' Amazon affiliate knowledge base (KSOR).\n\n"
    "FIRST, before doing anything else — including before searching — "
    "check if the question matches any of exactly these 5 topics: (1) "
    "returning or refunding a product, (2) canceling an order, (3) "
    "commission being reversed or clawed back, (4) the commission "
    "holding/payout period before a commission is final, (5) return "
    "windows. If it matches NONE of those 5 — e.g. product hunting, "
    "sourcing, listings, reviews, or anything else the knowledge base "
    "covers — do not search and do not answer it. Reply with exactly "
    "this and nothing else: \"I only handle refund and return "
    "questions — please ask the general assistant instead.\"\n\n"
    "If it matches any of the 5: answer strictly from the KSOR tools "
    "provided — never from general or pretrained knowledge. If the "
    "knowledge base does not cover it, say so plainly instead of "
    "guessing. Never include a URL or link in your answer unless that "
    "exact URL appears verbatim in the retrieved tool content — do not "
    "invent, guess, or generalize a link (e.g. a generic amazon.com URL) "
    "even if it sounds plausible."
)


async def run_refund_agent(query: str, session_id: str) -> str:
    session = SQLiteSession(session_id, REFUND_SESSIONS_DB)
    async with MCPServerStreamableHttp(
        name="KSOR",
        params={"url": MCP_URL},
        client_session_timeout_seconds=MCP_TIMEOUT_SECONDS,
    ) as ksor_server:
        agent = Agent(
            name="Refund Agent",
            instructions=INSTRUCTIONS,
            model=MODEL,
            # temperature=0: same reasoning as worker.py — this agent's
            # domain check needs to be consistent, not creative.
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
        )
        result = await Runner.run(agent, query, session=session)
        return result.final_output
