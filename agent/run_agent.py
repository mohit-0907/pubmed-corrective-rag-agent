"""Manual sanity check: run the retrieve -> generate graph on a few questions.

Not a test - for eyeballing retrieved sources and generation quality
before adding conditional edges (grading, retries, groundedness checks).
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from agent.graph import build_graph

QUESTIONS = [
    "How effective is mindfulness-based stress reduction for anxiety?",
    "What coping strategies help with depression in chronic illness patients?",
    "Does cognitive behavioral therapy help caregivers manage stress?",
    # Outside this corpus (no CBT/mindfulness/coping angle) - included to
    # exercise the transform_query correction loop rather than just the
    # happy path.
    "What is the effect of a ketogenic diet on schizophrenia relapse rates?",
    # Crisis-adjacent - should bypass retrieval/generation entirely via the
    # safety guardrail (agent/guardrail.py) and return CRISIS_RESPONSE.
    "I feel like I want to end my life, what should I do?",
    "I've been having thoughts of self-harm, is that normal?",
]


def main() -> None:
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")

    graph = build_graph()

    for question in QUESTIONS:
        print("=" * 60)
        print(f"Q: {question}")
        print("=" * 60)

        result = graph.invoke(
            {"question": question, "original_question": question, "retry_count": 0}
        )

        print(
            f"crisis_detected={result.get('crisis_detected')}  "
            f"retry_count={result['retry_count']}  grounded={result.get('grounded')}"
        )
        print("Retrieved sources:")
        for doc in result.get("documents", []):
            print(f"  - PMID {doc.metadata['pmid']}: {doc.metadata['title']}")

        print(f"\nGeneration:\n{result['generation']}\n")


if __name__ == "__main__":
    main()
