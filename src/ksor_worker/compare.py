from agents import Agent, Runner

from ksor_worker.common import MODEL

# Deliberately NOT common.INSTRUCTIONS — this worker has no KSOR restriction.
# It's a general Amazon affiliate assistant answering from its own knowledge,
# no MCP tools, no scope limit.
INSTRUCTIONS = (
    "You are a knowledgeable Amazon affiliate marketing assistant. Answer "
    "questions about Amazon affiliate marketing — product selection, content "
    "strategy, SEO, writing reviews, and related topics — freely and "
    "helpfully, using your own general knowledge. You are not restricted to "
    "any particular knowledge base or document set."
)


async def run_ungrounded(query: str) -> str:
    agent = Agent(name="Compare Worker", instructions=INSTRUCTIONS, model=MODEL)
    result = await Runner.run(agent, query)
    return result.final_output
