"""Graph node functions: retrieve and generate.

Each node is a small, single-purpose function that takes the current
GraphState and returns a partial state update, per LangGraph convention.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from agent.citations import citation_numbers_by_pmid, number_sources
from agent.graders import grade_documents_relevance, grade_hallucination, rewrite_query
from agent.guardrail import CRISIS_RESPONSE, is_crisis_message
from agent.state import GraphState
from data_pipeline.vector_store import load_vector_store

# Full-text papers average ~37 chunks against ~1.7 for abstract-only ones, so
# raw top-k lets a single well-matched paper occupy most of the context. We
# over-fetch, then keep at most MAX_CHUNKS_PER_PAPER from any one paper, which
# guarantees at least TOP_K / MAX_CHUNKS_PER_PAPER distinct sources.
RETRIEVE_CANDIDATES = 40
RETRIEVE_TOP_K = 12
MAX_CHUNKS_PER_PAPER = 2

GENERATION_MODEL = "gpt-4o"
# The rewrite is the text the user actually reads, and drift here would fail
# the groundedness check and trigger a retry - which costs more than the
# model difference saves. So the plain-language pass gets the strong model too.
SIMPLIFY_MODEL = "gpt-4o"

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
You are a research synthesis assistant working from published research on \
psychological coping strategies for depression, anxiety, and stress (CBT, \
mindfulness-based interventions, behavioral activation).

Answer the question using ONLY the provided sources. Each source is labelled \
with a number like [1]. Cite using those exact numbers - write [1] or [2][3] \
directly after the claim they support. Never invent a number that isn't in \
the sources, and never cite a PMID inline.

Where the sources give concrete detail - sample sizes, effect sizes, how long \
an intervention ran, who it was tested on - include it. That specificity is \
what makes the answer useful.

If the sources don't contain enough information to answer, say so plainly \
instead of guessing.

This is a research-synthesis tool, not a clinical tool - describe what studies \
found, never tell the reader what they personally should do."""

SIMPLIFY_SYSTEM_PROMPT = """\
Rewrite the research summary below so a reader with no medical or statistical \
background can follow it, aiming for the reading level of a good newspaper \
health article.

Rules:
- If the summary opens by directly answering the question ("Yes, ...", \
"No, ...", "There is limited evidence that..."), keep that opening. Turning a \
direct answer into a description makes the reader hunt for the answer, and \
reads as evasive even when the content is identical.
- Keep every [1]-style citation marker exactly where it belongs. Do not \
renumber, drop, or invent them.
- Explain a technical term the first time it appears, briefly and in passing \
- "behavioral activation (gradually rebuilding daily routines and activity)".
- Keep concrete numbers, but make them meaningful: "about 3 in 4 participants" \
reads better than "73.2%". Never change what a number says.
- Add nothing. Every fact must already be in the summary. If the summary says \
evidence is limited, the rewrite says so too.
- Short paragraphs. No headings, no bullet lists, no preamble like "Here is a \
simplified version".
- Stay descriptive, never prescriptive. Report what studies found; do not tell \
the reader what to do or imply a recommendation."""


@lru_cache(maxsize=1)
def _load_vector_store():
    # Loaded lazily and cached: importing this module shouldn't require
    # OPENAI_API_KEY / a built index to already exist, but once the graph
    # actually runs (e.g. inside a long-lived FastAPI process handling many
    # requests) we want one Pinecone client, not a fresh one per request.
    return load_vector_store()


@lru_cache(maxsize=1)
def _generation_llm() -> ChatOpenAI:
    return ChatOpenAI(model=GENERATION_MODEL, temperature=0)


@lru_cache(maxsize=1)
def _simplify_llm() -> ChatOpenAI:
    return ChatOpenAI(model=SIMPLIFY_MODEL, temperature=0)


def _format_context(documents: list[Document]) -> str:
    """Renders retrieved documents into a numbered, citable block for the prompt.

    Numbers come from agent.citations so the markers the model emits line up
    with the source list the API returns. Two chunks from the same paper share
    one number rather than appearing as separate sources.
    """
    numbers = citation_numbers_by_pmid(number_sources(documents))

    blocks = []
    for document in documents:
        meta = document.metadata
        number = numbers.get(meta.get("pmid", ""), 0)
        header = f"[{number}] {meta['title']} ({meta['journal']}, {meta['year']})"
        blocks.append(f"{header}\n{document.page_content}")
    return "\n\n".join(blocks)


def safety_check(state: GraphState) -> dict:
    """Screens the question for crisis language before any retrieval happens.

    Runs first in the graph, ahead of retrieve, so a flagged question never
    reaches the vector store or an LLM call - see agent/guardrail.py.
    """
    if is_crisis_message(state["question"]):
        return {"crisis_detected": True, "generation": CRISIS_RESPONSE}
    return {"crisis_detected": False}


def _cap_per_paper(documents: list[Document], top_k: int, per_paper: int) -> list[Document]:
    """Takes the best `top_k` chunks, allowing at most `per_paper` from each PMID.

    Walks in relevance order and skips a chunk once its paper has filled its
    quota, so ranking is preserved - this trims dominance rather than
    reshuffling results.
    """
    kept: list[Document] = []
    seen: dict[str, int] = {}

    for document in documents:
        pmid = document.metadata.get("pmid", "")
        if seen.get(pmid, 0) >= per_paper:
            continue
        seen[pmid] = seen.get(pmid, 0) + 1
        kept.append(document)
        if len(kept) == top_k:
            break

    return kept


def retrieve(state: GraphState) -> dict:
    """Fetches the most similar chunks, capped per source paper."""
    vector_store = _load_vector_store()
    candidates = vector_store.similarity_search(state["question"], k=RETRIEVE_CANDIDATES)
    documents = _cap_per_paper(candidates, RETRIEVE_TOP_K, MAX_CHUNKS_PER_PAPER)
    return {"documents": documents}


def grade_documents(state: GraphState) -> dict:
    """Filters retrieved documents down to those an LLM grades as relevant.

    Grades against original_question (what the user actually asked), not
    state["question"], since that may already be a retrieval-oriented
    rewrite from a previous transform_query pass.
    """
    documents = state["documents"]
    grades = grade_documents_relevance(
        [document.page_content for document in documents],
        state["original_question"],
    )
    return {
        "documents": [
            document for document, keep in zip(documents, grades, strict=True) if keep
        ]
    }


def transform_query(state: GraphState) -> dict:
    """Rewrites the search query when retrieval didn't turn up relevant documents."""
    new_question = rewrite_query(state["question"])
    return {"question": new_question, "retry_count": state["retry_count"] + 1}


def generate(state: GraphState) -> dict:
    """Synthesizes a cited but still technical answer from the documents.

    Deliberately not the final text: this stage optimises for fidelity to the
    sources, and simplify() then optimises for readability. Splitting them
    stops one prompt from having to trade those two goals off against each
    other, which is what produced the jargon-heavy output before.
    """
    context = _format_context(state["documents"])
    messages = [
        ("system", GENERATE_SYSTEM_PROMPT),
        ("human", f"Sources:\n\n{context}\n\nQuestion: {state['original_question']}"),
    ]
    response = _generation_llm().invoke(messages)

    return {"draft_generation": response.content}


def simplify(state: GraphState) -> dict:
    """Rewrites the technical draft into plain language, citations intact.

    Runs before check_groundedness rather than after, so the text that gets
    verified is the text the reader actually sees - verifying the draft and
    then rewriting it would leave the rewrite unchecked.
    """
    messages = [
        ("system", SIMPLIFY_SYSTEM_PROMPT),
        (
            "human",
            (
                f"Question: {state['original_question']}\n\n"
                f"Research summary:\n\n{state['draft_generation']}"
            ),
        ),
    ]
    response = _simplify_llm().invoke(messages)

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
