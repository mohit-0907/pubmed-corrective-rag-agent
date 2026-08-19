"""Graph node functions: retrieve and generate.

Each node is a small, single-purpose function that takes the current
GraphState and returns a partial state update, per LangGraph convention.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from agent.graders import grade_document_relevance, grade_hallucination, rewrite_query
from agent.guardrail import CRISIS_RESPONSE, is_crisis_message
from agent.state import GraphState
from data_pipeline.vector_store import load_vector_store

RETRIEVE_TOP_K = 5
GENERATION_MODEL = "gpt-4o"

DISCLAIMER_TEXT = (
    "This summary is drawn from published research literature for "
    "informational purposes only. It is not medical advice and is not a "
    "substitute for care from a qualified healthcare provider."
)
DISCLAIMER = f"\n\n---\n{DISCLAIMER_TEXT}"

UNGROUNDED_CAVEAT = (
    "\n\n[!] Note: parts of this answer could not be fully verified against "
    "the retrieved source abstracts."
)

GENERATE_SYSTEM_PROMPT = """\
You are a research synthesis assistant summarizing findings from PubMed \
abstracts about psychological coping strategies for depression, anxiety, \
and stress (CBT, mindfulness-based interventions, behavioral activation).

Answer the question using ONLY the provided abstracts. For every claim, \
cite the source using its PMID in the format (PMID: 12345678). If the \
abstracts don't contain enough information to answer the question, say so \
plainly instead of guessing.

This is a research-synthesis tool, not a clinical tool - do not give \
personal medical advice or tell the reader what they should do."""


@lru_cache(maxsize=1)
def _load_vector_store():
    # Loaded lazily and cached: importing this module shouldn't require
    # OPENAI_API_KEY / a built index to already exist, but once the graph
    # actually runs (e.g. inside a long-lived FastAPI process handling many
    # requests) we want one Chroma client, not a fresh one per request.
    return load_vector_store()


@lru_cache(maxsize=1)
def _generation_llm() -> ChatOpenAI:
    return ChatOpenAI(model=GENERATION_MODEL, temperature=0)


def _format_context(documents: list[Document]) -> str:
    """Renders retrieved documents into a citable block for the LLM prompt."""
    sections = []
    for doc in documents:
        meta = doc.metadata
        header = f"[PMID: {meta['pmid']}] {meta['title']} ({meta['journal']}, {meta['year']})"
        sections.append(f"{header}\n{doc.page_content}")
    return "\n\n".join(sections)


def safety_check(state: GraphState) -> dict:
    """Screens the question for crisis language before any retrieval happens.

    Runs first in the graph, ahead of retrieve, so a flagged question never
    reaches the vector store or an LLM call - see agent/guardrail.py.
    """
    if is_crisis_message(state["question"]):
        return {"crisis_detected": True, "generation": CRISIS_RESPONSE}
    return {"crisis_detected": False}


def retrieve(state: GraphState) -> dict:
    """Fetches the top-k most similar chunks for the (possibly rewritten) question."""
    vector_store = _load_vector_store()
    documents = vector_store.similarity_search(state["question"], k=RETRIEVE_TOP_K)
    return {"documents": documents}


def grade_documents(state: GraphState) -> dict:
    """Filters retrieved documents down to those an LLM grades as relevant.

    Grades against original_question (what the user actually asked), not
    state["question"], since that may already be a retrieval-oriented
    rewrite from a previous transform_query pass.
    """
    question = state["original_question"]
    filtered_docs = [
        doc
        for doc in state["documents"]
        if grade_document_relevance(doc.page_content, question)
    ]
    return {"documents": filtered_docs}


def transform_query(state: GraphState) -> dict:
    """Rewrites the search query when retrieval didn't turn up relevant documents."""
    new_question = rewrite_query(state["question"])
    return {"question": new_question, "retry_count": state["retry_count"] + 1}


def generate(state: GraphState) -> dict:
    """Synthesizes a cited answer from the retrieved documents."""
    llm = _generation_llm()
    context = _format_context(state["documents"])
    question = state["original_question"]

    messages = [
        ("system", GENERATE_SYSTEM_PROMPT),
        ("human", f"Abstracts:\n\n{context}\n\nQuestion: {question}"),
    ]
    response = llm.invoke(messages)

    return {"generation": response.content + DISCLAIMER}


def check_groundedness(state: GraphState) -> dict:
    """Grades whether the generation is supported by the retrieved documents.

    Also advances retry_count here (rather than only in transform_query),
    since this node is reached on every pass through the generate step -
    the shared counter caps total correction-loop iterations regardless of
    whether the next loop is a retry via transform_query or a regenerate.
    """
    documents_text = "\n\n".join(doc.page_content for doc in state["documents"])
    grounded = grade_hallucination(documents_text, state["generation"])
    return {"grounded": grounded, "retry_count": state["retry_count"] + 1}


def flag_ungrounded(state: GraphState) -> dict:
    """Appends a caveat when retries are exhausted and the answer is still ungrounded.

    Only reached via that specific routing branch (see routing.py) - the
    happy path and the "grounded but off-topic" exhausted-retries path
    don't go through this node.
    """
    generation = state["generation"].replace(DISCLAIMER, UNGROUNDED_CAVEAT + DISCLAIMER)
    return {"generation": generation}
