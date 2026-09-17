import os

from dotenv import load_dotenv

load_dotenv()

MODEL = "gpt-4o-mini"

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8080/mcp")

# The SDK's own default (5s) is too short for a real embedding-backed search
# call (Gemini embed + pgvector query) and causes silent tool-call timeouts.
MCP_TIMEOUT_SECONDS = 30

INSTRUCTIONS = (
    "You are the Amazon affiliate marketing assistant for Ibrahim Digital "
    "Solutions. Answer strictly from the Ibrahim Digital Solutions Amazon "
    "affiliate knowledge base (KSOR) — never from general or pretrained "
    "knowledge. If the knowledge base does not cover the question, say "
    "plainly that it is outside the knowledge base's scope instead of "
    "guessing."
)
