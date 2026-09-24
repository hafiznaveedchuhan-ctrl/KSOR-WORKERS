"""The golden-dataset contract. One `Case` per line of golden.jsonl.

Changing this file or a case's `expected` block changes what "correct" means,
so it is reviewed like an API change (see datasets/README.md).
"""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OPERATING_AGREEMENT_URL = "https://affiliate-program.amazon.com/help/operating/agreement"


class Category(StrEnum):
    grounded_qa = "grounded_qa"
    refund_domain = "refund_domain"
    abstention = "abstention"
    triage_routing = "triage_routing"
    refund_gate = "refund_gate"
    safety = "safety"
    roman_urdu = "roman_urdu"
    multi_turn = "multi_turn"


Endpoint = Literal[
    "ask", "chat", "refund", "triage", "compare",
    "gate",  # refund_gate.submit_refund / Inngest gate (deterministic)
    "unit",  # pure-code check, no LLM (e.g. is_refund_related)
]
Status = Literal["active", "known_failing", "blocked_until_stable"]


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stable_id: str  # e.g. "knowledge/refund-policy"
    quote: str | None = None  # verbatim from fixtures/kb_snapshot.json; None only for blocked_until_stable


class AuditExpect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str  # may contain "{uid}", replaced per run so a stale row can never satisfy a check
    action: Literal["refund_issued", "refund_blocked", "escalated_timeout"]
    present: bool = True  # False = this row must NOT exist


class Expected(BaseModel):
    model_config = ConfigDict(extra="forbid")
    behavior: str  # natural-language spec of correct behavior (the judge's reference)
    routed_to: str | None = None  # triage only: result.last_agent.name
    abstain: bool = False  # the correct answer is "the record does not cover this"
    exact_string: str | None = None  # answer must equal this after strip (decline / scope strings)
    must_include_all: list[str] = []  # case-insensitive substrings, every one required
    must_include_any: list[list[str]] = []  # each inner list: at least one alternative required
    must_not_include: list[str] = []  # case-insensitive substrings, none allowed
    forbid_urls_except: list[str] = [OPERATING_AGREEMENT_URL]  # any other URL in the answer = fabrication
    tools_expected: list[str] = []
    audit: list[AuditExpect] = []
    gate_triggered: bool | None = None  # unit cases: expected is_refund_related(query)
    event_sent: bool | None = None  # in-process gate cases: was refund/approval.requested sent?
    max_words: int | None = None  # the user asked for a short reply ("PLZ REPLY IN TWO LINE"); generous, not exact


class Turn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1)
    # gate cases only. decision=None -> submit_refund() in-process (no Inngest); otherwise the
    # live Inngest flow: send the requested event, then this decision, and read audit_log.db.
    request_id: str | None = None
    amount: float | None = None
    decision: Literal["approve", "reject", "wrong_id", "timeout"] | None = None
    send_fails: bool = False  # in-process only: simulate Inngest being unreachable


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    category: Category
    endpoint: Endpoint
    language: Literal["en", "roman_urdu"] = "en"
    difficulty: Literal["easy", "medium", "hard"]
    critical: bool = False  # a miss blocks the merge; bar = 3/3 repeats
    turns: list[Turn] = Field(min_length=1)  # >1 turn = one shared session_id, run in order
    source: Source | None = None
    origin: str | None = None  # the real failure/event that earned this case; required for hard/known cases
    expected: Expected
    unacceptable: list[str] = []  # human-readable "must never happen" (judge rubric input)
    status: Status = "active"
    repeats: int = Field(default=3, ge=1, le=10)
    authored_by: str
    reviewed_by: str | None = None  # the owner's sign-off; required before a baseline is recorded
    added_at: date
    notes: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> "Case":
        if self.category == Category.grounded_qa:
            if not (self.source and self.source.quote):
                raise ValueError("grounded_qa needs source.quote (verbatim from the served corpus)")
            if self.status != "active":
                raise ValueError("grounded_qa must be active")
        if self.status == "blocked_until_stable":
            if not self.source or self.source.quote:
                raise ValueError(
                    "blocked_until_stable: source.stable_id only, NO quote (draft text must not be copied into this repo)"
                )
            if not self.expected.abstain:
                raise ValueError("blocked_until_stable expects abstention while the source is unpublished")
        if self.status == "known_failing" and not self.origin:
            raise ValueError("known_failing needs origin (where the bug is documented)")
        if self.difficulty == "hard" and not self.origin:
            raise ValueError("hard cases must carry an origin (book: every hard case points at a real event)")
        if self.category in (Category.refund_gate, Category.safety) and not self.critical:
            raise ValueError(f"{self.category} cases are critical")
        if self.expected.abstain and self.expected.exact_string is None and not self.unacceptable:
            raise ValueError("abstain cases need `unacceptable` (what a leak from general knowledge looks like)")
        if self.category == Category.triage_routing and not self.expected.routed_to:
            raise ValueError("triage_routing needs expected.routed_to")
        if self.endpoint == "gate":
            t = self.turns[0]
            if t.request_id is None or t.amount is None:
                raise ValueError("gate cases need turns[0].request_id and .amount")
        if self.category == Category.multi_turn and len(self.turns) < 2:
            raise ValueError("multi_turn needs >= 2 turns")
        return self
