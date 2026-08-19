"""Compares the linear (Week 2) and corrective RAG graphs on a fixed eval set.

For each graph, runs every question in eval_questions.EVAL_QUESTIONS and
scores the answer with RAGAS (faithfulness, answer_relevancy,
context_precision). The crisis-adjacent question is handled separately -
it's not RAGAS-scored (a "should this even reach generation" check isn't
an answer-quality question), just checked for whether the graph correctly
bypassed retrieval/generation via the safety guardrail.

Outputs a markdown report to stdout and eval/results.md.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path

# Windows terminals often default stdout to cp1252, which can't encode
# characters this report uses (e.g. em dashes) - see data_pipeline scripts
# for the same fix.
sys.stdout.reconfigure(encoding="utf-8")

# ragas 0.4.3 unconditionally imports langchain_community.chat_models.vertexai
# at module load time just for an isinstance() check against a class we never
# use (we only use OpenAI models here). That submodule was removed from
# langchain-community (now being sunset in favor of standalone integration
# packages), so the real import fails before we ever get a chance to avoid
# it. Pre-registering a stub satisfies the import without needing Vertex AI
# installed or downgrading langchain-community (which would break the rest
# of the app - see conversation history for what that broke).
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _vertexai_stub = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:  # pragma: no cover - compatibility stub, never instantiated
        pass

    _vertexai_stub.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = _vertexai_stub

from dotenv import load_dotenv
from openai import AsyncOpenAI
from ragas.embeddings.base import embedding_factory
from ragas.llms.base import llm_factory
from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, Faithfulness

from agent.graph import build_graph
from agent.linear_graph import build_linear_graph
from agent.nodes import DISCLAIMER, UNGROUNDED_CAVEAT
from eval.eval_questions import EVAL_QUESTIONS

JUDGE_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
RESULTS_PATH = Path("eval/results.md")


def clean_answer(generation: str) -> str:
    """Strips the disclaimer/caveat boilerplate before handing text to RAGAS."""
    return generation.replace(DISCLAIMER, "").replace(UNGROUNDED_CAVEAT, "").strip()


def run_graph(graph, question: str) -> dict:
    return graph.invoke({"question": question, "original_question": question, "retry_count": 0})


async def safe_score(coro, label: str) -> float | None:
    """Runs one RAGAS metric, degrading to None (rather than crashing the
    whole eval run) when a metric can't be computed - e.g. context
    precision/faithfulness require non-empty retrieved_contexts, which the
    corrective graph can legitimately end up with after exhausting retries
    on an off-corpus question."""
    try:
        result = await coro
        return result.value
    except Exception as exc:  # noqa: BLE001 - any metric failure should degrade, not abort the run
        print(f"    RAGAS {label} skipped: {exc}")
        return None


async def score_answer(metrics, question: str, reference: str, answer: str, contexts: list[str]) -> dict:
    faithfulness, answer_relevancy, context_precision = metrics
    faithfulness_score, relevancy_score, precision_score = await asyncio.gather(
        safe_score(
            faithfulness.ascore(user_input=question, response=answer, retrieved_contexts=contexts),
            "faithfulness",
        ),
        safe_score(
            answer_relevancy.ascore(user_input=question, response=answer),
            "answer_relevancy",
        ),
        safe_score(
            context_precision.ascore(user_input=question, reference=reference, retrieved_contexts=contexts),
            "context_precision",
        ),
    )
    return {
        "faithfulness": faithfulness_score,
        "answer_relevancy": relevancy_score,
        "context_precision": precision_score,
    }


async def evaluate_graph(name: str, graph, metrics, questions: list[dict]) -> list[dict]:
    rows = []
    for i, item in enumerate(questions, start=1):
        question = item["question"]
        reference = item["reference"]
        category = item["category"]
        print(f"[{name}] {i}/{len(questions)}: {question[:60]}", flush=True)

        try:
            result = run_graph(graph, question)
        except Exception as exc:  # noqa: BLE001 - one bad question shouldn't abort the whole eval run
            print(f"  ERROR running graph: {exc}")
            rows.append(
                {"question": question, "category": category, "crisis_bypassed": False, "retry_count": 0, "scores": None}
            )
            continue

        crisis_bypassed = bool(result.get("crisis_detected"))
        documents = result.get("documents", [])
        retry_count = result.get("retry_count", 0)

        if category == "crisis":
            rows.append(
                {
                    "question": question,
                    "category": category,
                    "crisis_bypassed": crisis_bypassed,
                    "retry_count": retry_count,
                    "scores": None,
                }
            )
            continue

        contexts = [doc.page_content for doc in documents]
        answer = clean_answer(result.get("generation", ""))

        scores = await score_answer(metrics, question, reference, answer, contexts) if answer else None

        rows.append(
            {
                "question": question,
                "category": category,
                "crisis_bypassed": crisis_bypassed,
                "retry_count": retry_count,
                "scores": scores,
            }
        )

    return rows


def average(rows: list[dict], key: str) -> tuple[float, int]:
    values = [r["scores"][key] for r in rows if r["scores"] and r["scores"].get(key) is not None]
    if not values:
        return float("nan"), 0
    return sum(values) / len(values), len(values)


def format_report(linear_rows: list[dict], corrective_rows: list[dict]) -> str:
    lines = ["## RAGAS Evaluation: Linear vs. Corrective RAG", ""]

    lin_faith, lin_faith_n = average(linear_rows, "faithfulness")
    cor_faith, cor_faith_n = average(corrective_rows, "faithfulness")
    lin_rel, lin_rel_n = average(linear_rows, "answer_relevancy")
    cor_rel, cor_rel_n = average(corrective_rows, "answer_relevancy")
    lin_prec, lin_prec_n = average(linear_rows, "context_precision")
    cor_prec, cor_prec_n = average(corrective_rows, "context_precision")
    avg_retries = sum(r["retry_count"] for r in corrective_rows) / len(corrective_rows)

    lines += [
        "| Metric | Linear (Week 2) | Corrective |",
        "|---|---|---|",
        f"| Faithfulness | {lin_faith:.3f} (n={lin_faith_n}) | {cor_faith:.3f} (n={cor_faith_n}) |",
        f"| Answer Relevancy | {lin_rel:.3f} (n={lin_rel_n}) | {cor_rel:.3f} (n={cor_rel_n}) |",
        f"| Context Precision | {lin_prec:.3f} (n={lin_prec_n}) | {cor_prec:.3f} (n={cor_prec_n}) |",
        f"| Avg. retries used | — | {avg_retries:.2f} |",
        "",
        (
            "_n = number of the 14 non-crisis questions each metric could actually be scored "
            "on (RAGAS can't compute context precision/faithfulness with zero retrieved "
            "chunks, which the corrective graph can legitimately end up with after exhausting "
            "retries on an off-corpus question). The crisis-adjacent question is excluded from "
            "these averages entirely and reported separately below._"
        ),
        "",
    ]

    crisis_linear = next(r for r in linear_rows if r["category"] == "crisis")
    crisis_corrective = next(r for r in corrective_rows if r["category"] == "crisis")
    lines += [
        "### Safety guardrail check (crisis-adjacent question)",
        "",
        "| Graph | Bypassed RAG pipeline? |",
        "|---|---|",
        f"| Linear (Week 2) | {'Yes' if crisis_linear['crisis_bypassed'] else 'No - no guardrail exists on this graph; the question was sent straight through retrieval and generation'} |",
        f"| Corrective | {'Yes' if crisis_corrective['crisis_bypassed'] else 'No'} |",
        "",
        "### Per-question scores",
        "",
        "| # | Category | Question | Lin. Faith. | Lin. Rel. | Lin. Ctx.Prec. | Cor. Faith. | Cor. Rel. | Cor. Ctx.Prec. | Retries |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    def fmt(value):
        return f"{value:.2f}" if value is not None else "N/A"

    for i, (lr, cr) in enumerate(zip(linear_rows, corrective_rows), start=1):
        question_short = lr["question"][:55] + ("..." if len(lr["question"]) > 55 else "")
        if lr["category"] == "crisis":
            lines.append(f"| {i} | crisis | {question_short} | — | — | — | — | — | — | — |")
            continue
        ls = lr["scores"] or {}
        cs = cr["scores"] or {}
        lines.append(
            f"| {i} | {lr['category']} | {question_short} "
            f"| {fmt(ls.get('faithfulness'))} | {fmt(ls.get('answer_relevancy'))} | {fmt(ls.get('context_precision'))} "
            f"| {fmt(cs.get('faithfulness'))} | {fmt(cs.get('answer_relevancy'))} | {fmt(cs.get('context_precision'))} "
            f"| {cr['retry_count']} |"
        )

    return "\n".join(lines)


async def main() -> None:
    load_dotenv()

    client = AsyncOpenAI()
    llm = llm_factory(JUDGE_MODEL, client=client)
    embeddings = embedding_factory("openai", model=EMBEDDING_MODEL, client=client)
    metrics = (
        Faithfulness(llm=llm),
        AnswerRelevancy(llm=llm, embeddings=embeddings),
        ContextPrecision(llm=llm),
    )

    linear_graph = build_linear_graph()
    corrective_graph = build_graph()

    linear_rows = await evaluate_graph("linear", linear_graph, metrics, EVAL_QUESTIONS)
    corrective_rows = await evaluate_graph("corrective", corrective_graph, metrics, EVAL_QUESTIONS)

    report = format_report(linear_rows, corrective_rows)
    print("\n" + report)

    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(f"\nSaved to {RESULTS_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
