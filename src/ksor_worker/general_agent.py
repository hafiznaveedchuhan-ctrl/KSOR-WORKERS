"""The general-purpose assistant behind the site widget: answers anything
in the KSOR record — including refunds — from one agent with memory, no
domain split. `/ask` and `/refund` stay separate and narrower (see
CLAUDE.md rule 3/8) — this is a third, deliberately unrestricted-by-topic
option for a single chat surface."""

from agents import Agent, Runner, SQLiteSession
from agents.mcp import MCPServerStreamableHttp
from agents.model_settings import ModelSettings

from ksor_worker.common import INSTRUCTIONS, MCP_TIMEOUT_SECONDS, MCP_URL, MODEL

# Runtime state, not source — see .gitignore. Separate from
# refund_sessions.db so a /chat conversation and a /refund conversation
# for the same session_id never share history.
GENERAL_SESSIONS_DB = "general_sessions.db"


async def run_general_agent(query: str, session_id: str) -> str:
    session = SQLiteSession(session_id, GENERAL_SESSIONS_DB)
    async with MCPServerStreamableHttp(
        name="KSOR",
        params={"url": MCP_URL},
        client_session_timeout_seconds=MCP_TIMEOUT_SECONDS,
    ) as ksor_server:
        agent = Agent(
            name="General KSOR Assistant",
            instructions=INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
        )
        result = await Runner.run(agent, query, session=session)
        return result.final_output
