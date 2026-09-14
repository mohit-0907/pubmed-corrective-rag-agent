"""Compares plain RAG against the corrective graph on a fixed eval set.

Three arms, from two graph runs per question:

  linear            retrieve -> generate. No grading, no retries, no guardrail,
                    no plain-language rewrite. What the project was at Week 2.
  corrective_draft  The corrective loop's technical synthesis, before the
                    plain-language rewrite.
  corrective        The same run after simplify() - what a reader actually sees.

The last two come from a single corrective run, which is what makes the
simplify step measurable in isolation: same question, same retrieved context,
same draft, one rewrite between them.

Scored with RAGAS (faithfulness, answer relevancy, context precision) plus
Flesch readability - the metric the plain-language work actually targets, and
the one RAGAS has nothing to say about.

The crisis-adjacent question is never RAGAS-scored ("should this reach
generation at all" isn't an answer-quality question) and is reported
separately as a guardrail check.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import sys
import time
import types
from pathlib import Path

# Windows terminals often default stdout to cp1252, which can't encode
# characters this report uses (e.g. em dashes).
sys.stdout.reconfigure(encoding="utf-8")

# ragas 0.4.3 unconditionally imports langchain_community.chat_models.vertexai
# at module load time just for an isinstance() check against a class we never
# use. That submodule was removed from langchain-community, so the real import
# fails before we get a chance to avoid it. A stub satisfies it without
# downgrading langchain-community (which would break the rest of the app).
if "langchain_community.chat_models.vertexai" not in sys.modules:
    _vertexai_stub = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:  # pragma: no cover - compatibility stub, never instantiated
        pass

    _vertexai_stub.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = _vertexai_stub

import textstat
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
# RAGAS faithfulness decomposes an answer into atomic statements and runs NLI
# over each against the full retrieved context. With 12 chunks that output got
# truncated at the default limit, and the metric then failed outright - which
# silently scored only the shortest answers. Raised so the judge can finish.
JUDGE_MAX_TOKENS = 8000
EMBEDDING_MODEL = "text-embedding-3-small"
RESULTS_PATH = Path("eval/results.md")
RAW_PATH = Path("eval/results_raw.json")

ARMS = ("linear", "corrective_draft", "corrective")
ARM_LABELS = {
    "linear": "Linear (plain RAG)",
    "corrective_draft": "Corrective (draft)",
    "corrective": "Corrective (final)",
}


def strip_boilerplate(text: str) -> str:
    """Removes the disclaimer, caveat, and [1] markers before scoring.

    The disclaimer is identical across arms, so leaving it in would drag every
    readability score toward the same value and mask the differences we are
    trying to measure.
    """
    text = text.replace(DISCLAIMER, "").replace(UNGROUNDED_CAVEAT, "")
    text = re.sub(r"\[\d+\]", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def readability(text: str) -> dict:
    """Flesch-Kincaid grade level and Flesch reading ease. Deterministic, free."""
    clean = strip_boilerplate(text)
    if len(clean.split()) < 20:
        return {}
    return {
        "fk_grade": textstat.flesch_kincaid_grade(clean),
        "reading_ease": textstat.flesch_reading_ease(clean),
    }


async def safe_score(coro, label: str) -> float | None:
    """Runs one RAGAS metric, degrading to None rather than aborting the run."""
    try:
        result = await coro
        return result.value
    except Exception as exc:  # noqa: BLE001 - one metric failing shouldn't end the eval
        print(f"    RAGAS {label} skipped: {exc}")
        return None


async def score_arm(
    metrics,
    question: str,
    reference: str,
    answer: str,
    contexts: list[str],
    with_context_precision: bool = True,
) -> dict:
    """Scores one arm's answer.

    context_precision depends only on question/reference/contexts, so it is
    identical for the draft and final arms - computed once and shared rather
    than paying for the same judgement twice.
    """
    faithfulness, answer_relevancy, context_precision = metrics
    tasks = [
        safe_score(
            faithfulness.ascore(
                user_input=question, response=answer, retrieved_contexts=contexts
            ),
            "faithfulness",
        ),
        safe_score(
            answer_relevancy.ascore(user_input=question, response=answer),
            "answer_relevancy",
        ),
    ]
    if with_context_precision:
        tasks.append(
            safe_score(
                context_precision.ascore(
                    user_input=question, reference=reference, retrieved_contexts=contexts
                ),
                "context_precision",
            )
        )

    results = await asyncio.gather(*tasks)
    scores = {
        "faithfulness": results[0],
        "answer_relevancy": results[1],
        **readability(answer),
    }
    if with_context_precision:
        scores["context_precision"] = results[2]
    return scores


def run_graphs(linear_graph, corrective_graph, question: str) -> dict:
    """Runs one question through both graphs, returning all three arms' output."""
    initial = {"question": question, "original_question": question, "retry_count": 0}

    linear = linear_graph.invoke(dict(initial))
    started = time.time()
    corrective = corrective_graph.invoke(dict(initial))
    elapsed = time.time() - started

    corrective_contexts = [d.page_content for d in corrective.get("documents", [])]
    return {
        "linear": {
            "answer": linear.get("generation", ""),
            "contexts": [d.page_content for d in linear.get("documents", [])],
            "crisis_bypassed": bool(linear.get("crisis_detected")),
        },
        "corrective_draft": {
            "answer": corrective.get("draft_generation", ""),
            "contexts": corrective_contexts,
            "crisis_bypassed": bool(corrective.get("crisis_detected")),
        },
        "corrective": {
            "answer": corrective.get("generation", ""),
            "contexts": corrective_contexts,
            "crisis_bypassed": bool(corrective.get("crisis_detected")),
            "retry_count": corrective.get("retry_count", 0),
            "elapsed": elapsed,
        },
    }


async def evaluate(metrics, questions: list[dict]) -> list[dict]:
    """Runs and scores every question across all three arms."""
    linear_graph = build_linear_graph()
    corrective_graph = build_graph()
    rows: list[dict] = []

    for i, item in enumerate(questions, 1):
        question, reference, category = item["question"], item["reference"], item["category"]
        print(f"[{i}/{len(questions)}] {question[:62]}", flush=True)

        try:
            arms = run_graphs(linear_graph, corrective_graph, question)
        except Exception as exc:  # noqa: BLE001 - one bad question shouldn't abort the run
            print(f"  ERROR: {type(exc).__name__}: {exc}")
            continue

        if category != "crisis":
            for arm in ARMS:
                data = arms[arm]
                if not data["answer"]:
                    continue
                data["scores"] = await score_arm(
                    metrics,
                    question,
                    reference,
                    data["answer"],
                    data["contexts"],
                    with_context_precision=(arm != "corrective_draft"),
                )

        rows.append({"question": question, "category": category, "arms": arms})

    return rows


def average(rows: list[dict], arm: str, key: str) -> tuple[float, int]:
    """Mean of one metric for one arm, ignoring questions it couldn't be scored on."""
    values = [
        row["arms"][arm]["scores"][key]
        for row in rows
        if row["category"] != "crisis"
        and row["arms"][arm].get("scores", {}).get(key) is not None
    ]
    if not values:
        return float("nan"), 0
    return sum(values) / len(values), len(values)


def _metric_cell(rows: list[dict], arm: str, key: str) -> str:
    if key == "context_precision" and arm == "corrective_draft":
        return "_shared_"
    value, n = average(rows, arm, key)
    if math.isnan(value):
        return "n/a"
    return f"{value:.2f} (n={n})"


def format_report(rows: list[dict]) -> str:
    scored = [row for row in rows if row["category"] != "crisis"]
    lines = [
        "## Evaluation: plain RAG vs. corrective RAG",
        "",
        (
            f"{len(scored)} non-crisis questions. RAGAS scores run 0-1, higher is "
            "better. Flesch-Kincaid is a US school grade level (lower reads easier); "
            "reading ease runs 0-100 (higher reads easier)."
        ),
        "",
        "| Metric | " + " | ".join(ARM_LABELS[arm] for arm in ARMS) + " |",
        "|---|" + "---|" * len(ARMS),
    ]

    for key, label in (
        ("faithfulness", "Faithfulness"),
        ("answer_relevancy", "Answer relevancy"),
        ("context_precision", "Context precision"),
        ("fk_grade", "Flesch-Kincaid grade"),
        ("reading_ease", "Reading ease"),
    ):
        cells = [_metric_cell(rows, arm, key) for arm in ARMS]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")

    retries = [row["arms"]["corrective"].get("retry_count", 0) for row in scored]
    elapsed = [row["arms"]["corrective"].get("elapsed", 0.0) for row in scored]
    lines += [
        f"| Avg. retries | — | — | {sum(retries) / max(len(retries), 1):.2f} |",
        f"| Avg. latency | — | — | {sum(elapsed) / max(len(elapsed), 1):.1f}s |",
        "",
        (
            "_Context precision is a property of retrieval, so the draft and final "
            "arms share one value - the rewrite doesn't change which chunks were "
            "retrieved. n is how many questions each metric could be scored on: "
            "RAGAS cannot score faithfulness or context precision against zero "
            "retrieved chunks, which the corrective graph legitimately produces "
            "when it correctly declines an off-corpus question._"
        ),
        "",
        "### Safety guardrail check (crisis-adjacent question)",
        "",
        "| Graph | Bypassed the RAG pipeline? |",
        "|---|---|",
    ]

    crisis = next((row for row in rows if row["category"] == "crisis"), None)
    if crisis:
        for arm, graph_label in (("linear", "Linear"), ("corrective", "Corrective")):
            bypassed = crisis["arms"][arm]["crisis_bypassed"]
            verdict = (
                "Yes"
                if bypassed
                else "No - no guardrail on this graph; the question went straight "
                "through retrieval and generation"
            )
            lines.append(f"| {graph_label} | {verdict} |")

    lines += [
        "",
        "### Per-question readability and faithfulness",
        "",
        (
            "| # | Category | Question | Lin. FK | Draft FK | Final FK "
            "| Draft rel. | Final rel. | Draft faith. | Final faith. |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    def cell(row: dict, arm: str, key: str, places: int = 1) -> str:
        value = row["arms"][arm].get("scores", {}).get(key)
        return f"{value:.{places}f}" if value is not None else "—"

    for i, row in enumerate(rows, 1):
        question = row["question"][:46]
        if row["category"] == "crisis":
            lines.append(f"| {i} | crisis | {question} | — | — | — | — | — | — | — |")
            continue
        lines.append(
            f"| {i} | {row['category']} | {question} "
            f"| {cell(row, 'linear', 'fk_grade')} "
            f"| {cell(row, 'corrective_draft', 'fk_grade')} "
            f"| {cell(row, 'corrective', 'fk_grade')} "
            f"| {cell(row, 'corrective_draft', 'answer_relevancy', 2)} "
            f"| {cell(row, 'corrective', 'answer_relevancy', 2)} "
            f"| {cell(row, 'corrective_draft', 'faithfulness', 2)} "
            f"| {cell(row, 'corrective', 'faithfulness', 2)} |"
        )

    return "\n".join(lines)


async def main() -> None:
    load_dotenv()

    client = AsyncOpenAI()
    llm = llm_factory(JUDGE_MODEL, client=client, max_tokens=JUDGE_MAX_TOKENS)
    embeddings = embedding_factory("openai", model=EMBEDDING_MODEL, client=client)
    metrics = (
        Faithfulness(llm=llm),
        AnswerRelevancy(llm=llm, embeddings=embeddings),
        ContextPrecision(llm=llm),
    )

    rows = await evaluate(metrics, EVAL_QUESTIONS)
    report = format_report(rows)
    print("\n" + report)

    RESULTS_PATH.write_text(report, encoding="utf-8")

    # Raw scores and answers, so an unexpected aggregate can be traced back to
    # the questions driving it without paying for another full run. The first
    # version of this script kept only the formatted report, which meant every
    # follow-up question about a number cost 15 minutes and another eval.
    RAW_PATH.write_text(
        json.dumps(
            [
                {
                    "question": row["question"],
                    "category": row["category"],
                    "arms": {
                        arm: {
                            "answer": row["arms"][arm].get("answer", ""),
                            "scores": row["arms"][arm].get("scores", {}),
                        }
                        for arm in ARMS
                    },
                }
                for row in rows
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nSaved to {RESULTS_PATH} and {RAW_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
