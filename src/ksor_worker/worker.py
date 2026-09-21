from agents import Agent, Runner
from agents.mcp import MCPServerStreamableHttp
from agents.model_settings import ModelSettings

from ksor_worker.common import INSTRUCTIONS, MCP_TIMEOUT_SECONDS, MCP_URL, MODEL


async def run_grounded(query: str) -> str:
    async with MCPServerStreamableHttp(
        name="KSOR",
        params={"url": MCP_URL},
        client_session_timeout_seconds=MCP_TIMEOUT_SECONDS,
    ) as ksor_server:
        agent = Agent(
            name="KSOR Worker",
            instructions=INSTRUCTIONS,
            model=MODEL,
            # temperature=0: this agent's first job is a binary in/out-of-
            # scope classification (the refund carve-out) before it ever
            # answers anything — that needs to be consistent, not creative.
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
        )
        result = await Runner.run(agent, query)
        return result.final_output
