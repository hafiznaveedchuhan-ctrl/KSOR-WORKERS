"""LLM-judge layer: DeepEval (output quality) + Ragas (retrieval vs grounding), on top of the
deterministic graders — never instead of them.

Judge model != agent model (book, Decision 2: avoid self-grading bias). The agents run gpt-4o-mini, so the
judge defaults to gpt-4o; override with EVAL_JUDGE_MODEL. Metrics are ADVISORY until the judge has been
calibrated against the owner (scripts/calibrate_judge.py) — see docs/critical-metrics.md.

DeepEval 4.x names: SingleTurnParams (was LLMTestCaseParams), GEval for task-specific rubrics.
Run through plain `pytest`, not `deepeval test run` (the book notes the CLI can hang).
"""

import json
import os
from dataclasses import dataclass, field

import httpx

JUDGE_MODEL = os.environ.get("EVAL_JUDGE_MODEL", "gpt-4o")
AGENT_MODEL = "gpt-4o-mini"  # ksor_worker.common.MODEL — kept literal so a judge==agent mistake is loud
MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8080/mcp")

assert JUDGE_MODEL != AGENT_MODEL, "judge must not be the agent's own model (self-grading bias)"


@dataclass
class Score:
    metric: str
    score: float | None
    passed: bool | None
    reason: str = ""


@dataclass
class Retrieval:
    contexts: list[str] = field(default_factory=list)
    slugs: list[str] = field(default_factory=list)
    generation: int | None = None


def retrieve(query: str, k: int = 5) -> Retrieval:
    """Call the served KSOR MCP `search` tool directly, so retrieval can be judged separately from the
    agent's answer. Stateless streamable-HTTP JSON-RPC; no session needed against this server."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "search", "arguments": {"query": query, "k": k}}}
    resp = httpx.post(MCP_URL, json=body, headers={"accept": "application/json, text/event-stream"}, timeout=60)
    resp.raise_for_status()
    line = next(x for x in resp.text.splitlines() if x.startswith("data: "))
    result = json.loads(line[6:])["result"]
    payload = result.get("structuredContent") or json.loads(result["content"][0]["text"])
    hits = payload.get("hits") or payload.get("results") or []
    return Retrieval(
        contexts=[h["content"] for h in hits],
        slugs=[h.get("slug", "") for h in hits],
        generation=(hits[0].get("provenance") or {}).get("generation") if hits else None,
    )


# --------------------------------------------------------------------------- DeepEval
def deepeval_scores(question: str, answer: str, contexts: list[str], expected_behavior: str, *, abstain: bool) -> list[Score]:
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval, HallucinationMetric
    from deepeval.test_case import LLMTestCase, SingleTurnParams

    case = LLMTestCase(input=question, actual_output=answer, expected_output=expected_behavior,
                       context=contexts, retrieval_context=contexts)
    metrics = [
        ("answer_relevancy", AnswerRelevancyMetric(threshold=0.7, model=JUDGE_MODEL)),
        ("faithfulness", FaithfulnessMetric(threshold=0.8, model=JUDGE_MODEL)),
        ("hallucination", HallucinationMetric(threshold=0.3, model=JUDGE_MODEL)),
        ("scope_and_honesty", GEval(
            name="ScopeAndHonesty",
            criteria=(
                "Judge ONLY against the expected behavior. Fail if the answer states facts the retrieved context does not "
                "contain, if it answers an out-of-scope or uncovered question from general knowledge, if it presents a scope "
                "boundary as a temporary outage, or if it claims a refund was issued when it is only pending."
            ),
            evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
            threshold=0.7, model=JUDGE_MODEL,
        )),
    ]
    out: list[Score] = []
    for name, m in metrics:
        if abstain and name in ("faithfulness", "answer_relevancy"):
            continue  # an honest abstention has no claims to ground and is not "relevant" in the usual sense
        try:
            m.measure(case)
            out.append(Score(name, m.score, m.is_successful(), getattr(m, "reason", "") or ""))
        except Exception as exc:  # judge/API failure is an ERROR of the judge, never a pass
            out.append(Score(name, None, None, f"judge error: {type(exc).__name__}: {exc}"))
    return out


# --------------------------------------------------------------------------- Ragas
def ragas_scores(question: str, answer: str, contexts: list[str], reference: str) -> list[Score]:
    """Retrieval (context relevance/recall) vs grounding (faithfulness) vs correctness, separated so a
    failure points at the right layer: prompt, retrieval, or the knowledge base itself."""
    import asyncio

    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerCorrectness, ContextRecall, ContextRelevance, Faithfulness

    client = AsyncOpenAI()
    llm = llm_factory(JUDGE_MODEL, client=client)
    emb = embedding_factory("openai", model="text-embedding-3-small", client=client)

    async def run() -> list[Score]:
        out: list[Score] = []
        jobs = {
            "context_relevance": lambda: ContextRelevance(llm=llm).ascore(user_input=question, retrieved_contexts=contexts),
            "faithfulness": lambda: Faithfulness(llm=llm).ascore(user_input=question, response=answer, retrieved_contexts=contexts),
            "context_recall": lambda: ContextRecall(llm=llm).ascore(user_input=question, retrieved_contexts=contexts, reference=reference),
            "answer_correctness": lambda: AnswerCorrectness(llm=llm, embeddings=emb).ascore(user_input=question, response=answer, reference=reference),
        }
        for name, job in jobs.items():
            try:
                res = await job()
                out.append(Score(name, float(res.value), None))
            except Exception as exc:
                out.append(Score(name, None, None, f"judge error: {type(exc).__name__}: {exc}"))
        return out

    return asyncio.run(run())
