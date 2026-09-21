import os

from dotenv import load_dotenv

load_dotenv()

MODEL = "gpt-4o-mini"

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8080/mcp")

# The SDK's own default (5s) is too short for a real embedding-backed search
# call (Gemini embed + pgvector query) and causes silent tool-call timeouts.
MCP_TIMEOUT_SECONDS = 30

# Origins the /refund endpoint's browser widget is allowed to call from.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

# A deterministic backstop for worker.py's refund carve-out. Prompt-only
# enforcement of this rule was tested and found unreliable — gpt-4o-mini
# answered a plainly refund-worded question directly on 3/3 repeated calls
# despite an explicit instruction not to (see progress.md). A keyword match
# on the obvious cases is checked in code, before the agent ever runs, so
# the common case is guaranteed correct; the prompt instruction remains as
# a second layer for refund-adjacent phrasing this list doesn't catch.
REFUND_KEYWORDS = (
    "refund",
    "return",
    "returned",
    "returning",
    "cancel",
    "cancellation",
    "cancelled",
    "canceled",
    "reversed",
    "reversal",
    "chargeback",
    "clawback",
)


def is_refund_related(query: str) -> bool:
    lowered = query.lower()
    return any(keyword in lowered for keyword in REFUND_KEYWORDS)


# Single source for this exact string — used both in worker.py's prompt
# (for refund-adjacent phrasing the keyword list above doesn't catch) and
# as the literal response main.py returns when the keyword check fires, so
# the two paths can never say something different for the same rule.
REFUND_DECLINE_MESSAGE = (
    "That's a refund/return question — please ask the refund assistant instead."
)

INSTRUCTIONS = (
    "You are the Amazon affiliate marketing assistant for Ibrahim Digital "
    "Solutions.\n\n"
    "FIRST, before doing anything else — including before searching — "
    "check if the question matches any of exactly these 5 topics: (1) "
    "returning or refunding a product, (2) canceling an order, (3) "
    "commission being reversed or clawed back, (4) the commission "
    "holding/payout period before a commission is final, (5) return "
    "windows. If it matches ANY of those 5, do not search and do not "
    f'answer it — reply with exactly this and nothing else: "{REFUND_DECLINE_MESSAGE}" '
    "A question that only mentions commissions, earnings, or payouts in "
    "general — with no return, refund, cancellation, reversal, or "
    "holding-period angle — does NOT match and should be answered "
    "normally.\n\n"
    "For every other question: answer strictly from the Ibrahim Digital "
    "Solutions Amazon affiliate knowledge base (KSOR) — never from "
    "general or pretrained knowledge. If the knowledge base does not "
    "cover the question, say plainly that it is outside the knowledge "
    "base's scope instead of guessing."
)
