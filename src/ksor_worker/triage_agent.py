"""Real orchestration: one TriageAgent receives every query and hands off
to a specialist Agent using the SDK's own `handoffs` mechanism — never a
keyword if/else pretending to be one. See docs/adr/005-triage-handoffs.md
for the architectural mismatch this file works around: a handoff target
must be a single Agent instance, but eval_agent.py/policy_agent.py/
router_agent.py are two-step Python pipelines, not Agents. Those three
CLI tools stay completely untouched; the three specialists below
(PolicySpecialist, EvalSpecialist, RouterSpecialist) are new, deliberately
simpler single-call versions of the same roles, built only for handoff.

Every specialist is wrapped in `handoff(..., input_filter=remove_all_tools)`
— found necessary live, not by inspection: the SDK's default handoff passes
the specialist the triage agent's own `transfer_to_x` tool-call and its
JSON output as prior context, and that clutter derailed
RefundSpecialist's strict "does this match exactly these 5 topics" check —
it declined "When will I get my refund?" (a plain match) 3/3 with the
default, unfiltered handoff, and answered it correctly 3/3 once each
handoff stripped that tool-call noise before the specialist sees it."""

import asyncio
import uuid

from agents import Agent, AgentsException, Runner, SQLiteSession, handoff
from agents.extensions import handoff_filters
from agents.mcp import MCPServerStreamableHttp
from agents.model_settings import ModelSettings
from mcp.shared.exceptions import MCPError

from ksor_worker.common import INSTRUCTIONS, MCP_TIMEOUT_SECONDS, MCP_URL, MODEL
from ksor_worker.refund_agent import INSTRUCTIONS as REFUND_INSTRUCTIONS

# Runtime state, not source — see .gitignore. Separate from
# refund_sessions.db/general_sessions.db, same reasoning as those two: a
# triage conversation and a /chat or /refund conversation for the same
# session_id must never share history.
TRIAGE_SESSIONS_DB = "triage_sessions.db"

POLICY_SPECIALIST_INSTRUCTIONS = (
    "You are the sensitive-data specialist for Ibrahim Digital Solutions' "
    "Amazon affiliate knowledge base (KSOR). The query you receive may "
    "contain personally identifiable or sensitive information — full "
    "names, email addresses, phone numbers, financial data (card/account "
    "numbers, amounts tied to a named account), or passwords/credentials.\n\n"
    "Before answering, silently form a redacted version of the query in "
    "your own understanding, with every sensitive span replaced by a "
    "bracketed placeholder matching its type ([NAME], [EMAIL], [PHONE], "
    "[FINANCIAL], [PASSWORD]) — then answer strictly from the KSOR tools "
    "provided, using only that redacted intent. Never repeat the raw "
    "sensitive value back in your answer, not even to confirm you saw it. "
    "If the knowledge base does not cover the (redacted) question, say so "
    "plainly instead of guessing. Never include a URL or link in your "
    "answer unless that exact URL appears verbatim in the retrieved tool "
    "content — do not invent, guess, or generalize a link even if it "
    "sounds plausible."
)

EVAL_SPECIALIST_INSTRUCTIONS = (
    "You are the answer-verification specialist for Ibrahim Digital "
    "Solutions' Amazon affiliate knowledge base (KSOR). Answer the query "
    "strictly from the KSOR tools provided — never from general or "
    "pretrained knowledge. If the knowledge base does not cover it, say so "
    "plainly instead of guessing. Never include a URL or link unless that "
    "exact URL appears verbatim in the retrieved tool content.\n\n"
    "Then, on a new line, append exactly: \"Groundedness check: <VERDICT> "
    "— <one-sentence reason>\", where <VERDICT> MUST be exactly one of "
    "these three tokens — GROUNDED, PARTIALLY_GROUNDED, HALLUCINATED — and "
    "never any other word (never ABSTAINED, UNVERIFIED, UNKNOWN, N/A, or "
    "anything else). GROUNDED means every claim in your answer is "
    "supported by what the tools returned, OR your answer is a clean "
    "abstention (the knowledge base doesn't cover it, and you said so "
    "instead of guessing) — an honest abstention is always GROUNDED, never "
    "a separate category and never HALLUCINATED. PARTIALLY_GROUNDED means "
    "some claims are supported, others are not verifiable from the tool "
    "output. HALLUCINATED means a claim contradicts or has no basis "
    "anywhere in the tool output. Self-assess honestly against only what "
    "the tools actually returned, not against what you already believe to "
    "be true."
)

ROUTER_SPECIALIST_INSTRUCTIONS = (
    "You are the model-selection specialist for Ibrahim Digital Solutions. "
    "You do not answer questions about Amazon affiliate marketing content "
    "at all — you only give model-selection advice.\n\n"
    "The query you receive IS the task to classify — it may be phrased as "
    "a bare task description (\"summarize this 40-page document\"), or as "
    "a question that already names or describes the task inline (\"which "
    "model should I use for a complex multi-step reasoning task?\", "
    "\"gpt-4o-mini or gpt-4o for X?\"). Either phrasing is enough — read "
    "whatever task description is embedded in the query itself and "
    "classify THAT. Do not ask for more detail and do not treat a query "
    "that already names its own complexity (\"simple\", \"complex\", "
    "\"multi-step\", \"one-step\", etc.) as too vague to classify.\n\n"
    "Classify it as \"simple\" (a short, factual, single-step lookup with "
    "one clear answer — recommend gpt-4o-mini) or \"complex\" (requires "
    "multi-step reasoning, comparing multiple things, or synthesizing "
    "several facts together — recommend gpt-4o). State the classification, "
    "the recommended model, and a one-sentence reason.\n\n"
    "Only decline — saying so and suggesting the general assistant "
    "instead — if the query has nothing at all to do with choosing "
    "between AI models (e.g. it is actually a KSOR content question, a "
    "refund question, or contains no task of any kind to classify)."
)

TRIAGE_INSTRUCTIONS = (
    "You are the triage agent for Ibrahim Digital Solutions' Amazon "
    "affiliate assistant. You never answer directly — your only job is to "
    "hand off to exactly one specialist, on every turn, using these rules "
    "in order:\n"
    "1. If the query is about refunds, returns, cancellations, or "
    "commission reversal/clawback — hand off to RefundSpecialist.\n"
    "2. Else if the query contains or asks about personal data (a name, "
    "email, phone number, financial/account info, or a password) — hand "
    "off to PolicySpecialist.\n"
    "3. Else if the query asks you to check, verify, or validate a "
    "previous answer for hallucination or groundedness — hand off to "
    "EvalSpecialist.\n"
    "4. Else if the query asks which AI model to use for a task — hand "
    "off to RouterSpecialist.\n"
    "5. Otherwise — hand off to KSORWorker for general Amazon affiliate "
    "knowledge questions.\n"
    "Always hand off; never answer the query yourself."
)


async def run_triage_agent(query: str, session_id: str) -> tuple[str, str]:
    session = SQLiteSession(session_id, TRIAGE_SESSIONS_DB)
    async with MCPServerStreamableHttp(
        name="KSOR",
        params={"url": MCP_URL},
        client_session_timeout_seconds=MCP_TIMEOUT_SECONDS,
    ) as ksor_server:
        ksor_worker = Agent(
            name="KSORWorker",
            instructions=INSTRUCTIONS,
            model=MODEL,
            # tool_choice="required": found live that, in a multi-specialist
            # triage session, a PRIOR turn's decline from a different
            # specialist (e.g. RefundSpecialist's "please ask the general
            # assistant instead") can prime this agent to skip the search
            # tool entirely and self-decline an unrelated, clearly in-scope
            # question — reproduced with plain Agent+Runner.run() given
            # that exact history, no triage/handoff machinery involved.
            # Forcing a tool call is safe here specifically because
            # KSORWorker is only ever reached once TriageAgent has already
            # decided this is an answerable general-knowledge question — it
            # has no legitimate reason to answer without searching first.
            # See docs/adr/005-triage-handoffs.md.
            model_settings=ModelSettings(temperature=0, tool_choice="required"),
            mcp_servers=[ksor_server],
            handoff_description="General Amazon affiliate knowledge questions",
        )
        refund_specialist = Agent(
            name="RefundSpecialist",
            instructions=REFUND_INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
            handoff_description=(
                "Refunds, returns, cancellations, commission reversal"
            ),
        )
        policy_specialist = Agent(
            name="PolicySpecialist",
            instructions=POLICY_SPECIALIST_INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
            handoff_description=(
                "Queries containing sensitive personal data — names, "
                "emails, phone numbers, financial info"
            ),
        )
        eval_specialist = Agent(
            name="EvalSpecialist",
            instructions=EVAL_SPECIALIST_INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            mcp_servers=[ksor_server],
            handoff_description=(
                "Requests to verify, validate, or check a previous answer "
                "for hallucination"
            ),
        )
        router_specialist = Agent(
            name="RouterSpecialist",
            instructions=ROUTER_SPECIALIST_INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            # No MCP tools: this specialist advises on model choice, it
            # never answers from the KSOR record.
            handoff_description="Questions about which AI model to use for a task",
        )
        triage_agent = Agent(
            name="TriageAgent",
            instructions=TRIAGE_INSTRUCTIONS,
            model=MODEL,
            model_settings=ModelSettings(temperature=0),
            # remove_all_tools: strip the triage agent's own handoff
            # tool-call/output from what each specialist sees — see the
            # module docstring for the live bug this fixed.
            handoffs=[
                handoff(ksor_worker, input_filter=handoff_filters.remove_all_tools),
                handoff(refund_specialist, input_filter=handoff_filters.remove_all_tools),
                handoff(policy_specialist, input_filter=handoff_filters.remove_all_tools),
                handoff(eval_specialist, input_filter=handoff_filters.remove_all_tools),
                handoff(router_specialist, input_filter=handoff_filters.remove_all_tools),
            ],
        )
        result = await Runner.run(triage_agent, query, session=session)
        return result.final_output, result.last_agent.name


async def _cli() -> None:
    """Standalone terminal test harness — same pattern as eval_agent.py/
    policy_agent.py/router_agent.py's own _cli(). One session per CLI run,
    so consecutive questions in the same run share triage memory, matching
    how the /triage endpoint behaves within one session_id."""
    print("Triage agent (real SDK handoffs — see docs/adr/005-triage-handoffs.md).")
    print("Type 'exit' to quit.\n")
    session_id = str(uuid.uuid4())
    while True:
        query = input("You: ").strip()
        if query.lower() in {"exit", "quit"}:
            break
        if not query:
            continue
        try:
            answer, routed_to = await run_triage_agent(query, session_id)
        except (MCPError, AgentsException) as exc:
            print(f"\n[error] KSOR MCP server unavailable: {exc}\n")
            continue
        print(f"\nRouted to: {routed_to}")
        print(f"Answer: {answer}\n")


if __name__ == "__main__":
    asyncio.run(_cli())
