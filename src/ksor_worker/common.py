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


# Single source for this exact string — every caller that short-circuits on
# is_refund_related() returns this, so the message can never drift between
# call sites.
REFUND_DECLINE_MESSAGE = (
    "That's a refund/return question — please ask the refund assistant instead."
)

# INSTRUCTIONS deliberately carries NO refund-related clause — that was
# tried and made things worse, not better. A prompt-embedded "if this is
# about refunds, reply with X" instruction was found (2026-09-21) to also
# make the model answer PLAINLY UNRELATED questions (e.g. "Who won the
# cricket world cup?") with the refund decline text, 3 times out of 4 on
# repeated calls — the model was conflating "I shouldn't answer this" in
# general with "this specifically matches the refund carve-out," because
# both were phrased as similar-looking escape-hatch templates in one
# prompt. Removing the clause entirely and relying solely on
# is_refund_related() as a pre-call gate (in main.py and in every agent
# that reuses these INSTRUCTIONS) fixed the false positive. The accepted
# trade-off: a genuinely refund-adjacent question with no matching keyword
# (e.g. "how long until my commission is final?") is no longer redirected
# — it gets answered normally from KSOR content instead, which is a minor,
# low-stakes gap next to the bug it replaced. Full sequence in
# docs/adr/003-refund-agent-memory.md.
INSTRUCTIONS = (
    "You are the Amazon affiliate marketing assistant for Ibrahim Digital "
    "Solutions. Answer strictly from the Ibrahim Digital Solutions Amazon "
    "affiliate knowledge base (KSOR) — never from general or pretrained "
    "knowledge. If the knowledge base does not cover the question, say "
    "plainly that it is outside the knowledge base's scope instead of "
    "guessing."
)
