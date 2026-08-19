"""CI smoke test: confirms the compiled corrective graph runs end to end
without throwing, given a test question.

Every LLM/embedding/vector-store call is mocked, so this needs no API key,
no built Chroma index, and no network access - it runs in well under a
second. This checks that the graph is wired correctly (nodes/edges/state
flow don't crash), not answer quality - that's what eval/run_eval.py is
for, deliberately not run on every push.

Patch targets matter here: nodes.py and routing.py do
`from agent.graders import grade_document_relevance, ...`, which binds
those names into *their own* module namespaces. Patching
agent.graders.grade_document_relevance would not affect what nodes.py
actually calls - the patch has to target agent.nodes.grade_document_relevance
(and agent.routing.grade_answer) instead.
"""

from __future__ import annotations

from langchain_core.documents import Document

from agent import nodes, routing
from agent.graph import build_graph

TEST_QUESTION = "How effective is mindfulness-based stress reduction for anxiety?"


class _FakeVectorStore:
    def similarity_search(self, query: str, k: int) -> list[Document]:
        return [
            Document(
                page_content=(
                    "Mindfulness-based stress reduction significantly reduced "
                    "anxiety symptoms in the study population."
                ),
                metadata={
                    "pmid": "12345678",
                    "title": "A fake but plausible study title",
                    "journal": "Fake Journal of Testing",
                    "year": "2024",
                },
            )
        ]


class _FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeGenerationLLM:
    def invoke(self, messages) -> _FakeLLMResponse:
        return _FakeLLMResponse(
            "Mindfulness-based stress reduction is effective for anxiety (PMID: 12345678)."
        )


def test_corrective_graph_runs_end_to_end(monkeypatch):
    monkeypatch.setattr(nodes, "_load_vector_store", lambda: _FakeVectorStore())
    monkeypatch.setattr(nodes, "_generation_llm", lambda: _FakeGenerationLLM())
    monkeypatch.setattr(nodes, "grade_document_relevance", lambda document, question: True)
    monkeypatch.setattr(nodes, "grade_hallucination", lambda documents, generation: True)
    monkeypatch.setattr(routing, "grade_answer", lambda question, generation: True)

    graph = build_graph()
    result = graph.invoke(
        {
            "question": TEST_QUESTION,
            "original_question": TEST_QUESTION,
            "retry_count": 0,
        }
    )

    assert result["generation"]
    assert "12345678" in result["generation"]
    assert result["crisis_detected"] is False
    assert len(result["documents"]) == 1


def test_safety_guardrail_bypasses_graph_for_crisis_question(monkeypatch):
    # Sanity check that the fakes above are never even reached on this path -
    # if the guardrail didn't fire, this would hang/fail trying to call the
    # unmocked graders on a nonsense document set.
    monkeypatch.setattr(nodes, "_load_vector_store", lambda: _FakeVectorStore())
    monkeypatch.setattr(nodes, "_generation_llm", lambda: _FakeGenerationLLM())

    question = "I feel like I want to end my life, what should I do?"
    graph = build_graph()
    result = graph.invoke({"question": question, "original_question": question, "retry_count": 0})

    assert result["crisis_detected"] is True
    assert result.get("documents", []) == []
    assert "988" in result["generation"]
