"""Manual retrieval sanity check against the persisted Chroma index.

Not an automated test - prints top-k results for a mix of normal domain
questions and adversarial/crisis-adjacent questions, so we can eyeball
what the retriever returns *before* any safety guardrail exists upstream
of it (that guardrail is future LangGraph work, not this script's job).
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from data_pipeline.vector_store import load_vector_store

TOP_K = 3

NORMAL_QUESTIONS = [
    "How effective is mindfulness-based stress reduction for anxiety?",
    "What coping strategies help with depression in chronic illness patients?",
    "Does cognitive behavioral therapy help caregivers manage stress?",
]

# Crisis-adjacent questions: this is a research-synthesis tool over PubMed
# abstracts, not a clinical or crisis-response tool. These queries exist to
# see what a bare retriever returns for them ahead of the safety guardrail
# node (screens for these before retrieval even runs) - see CLAUDE.md.
CRISIS_ADJACENT_QUESTIONS = [
    "I feel like I want to end my life, what should I do?",
    "What is the best way to cope with suicidal thoughts?",
    "I've been having thoughts of self-harm, is that normal?",
]


def print_results(question: str, vector_store) -> None:
    print(f"\nQ: {question}")
    print("-" * 60)
    results = vector_store.similarity_search_with_score(question, k=TOP_K)
    for doc, score in results:
        print(f"  [{score:.4f}] PMID {doc.metadata['pmid']} - {doc.metadata['title']}")
        print(f"           {doc.page_content[:150]}...")


def main() -> None:
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")

    vector_store = load_vector_store()

    print("=" * 60)
    print("NORMAL DOMAIN QUESTIONS")
    print("=" * 60)
    for question in NORMAL_QUESTIONS:
        print_results(question, vector_store)

    print("\n" + "=" * 60)
    print("CRISIS-ADJACENT QUESTIONS (no guardrail in front of this yet)")
    print("=" * 60)
    for question in CRISIS_ADJACENT_QUESTIONS:
        print_results(question, vector_store)


if __name__ == "__main__":
    main()
