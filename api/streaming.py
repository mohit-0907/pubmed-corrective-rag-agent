"""SSE event generation for the streaming /query/stream endpoint.

Kept separate from api/main.py: this is genuinely different-shaped logic
(an async generator producing wire-format strings) from route wiring, and
it needs its own per-node "what happened" descriptions that have nothing
to do with the request/response schema in api/schemas.py.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from agent.nodes import DISCLAIMER, DISCLAIMER_TEXT


def _describe_node_update(node_name: str, prior_state: dict, update: dict) -> str:
    """Renders a human-readable summary of what a node just did.

    Some descriptions (grade_documents) need the state *before* this
    update was applied - e.g. to say "3 of 5 kept" rather than just "3
    kept" - so both prior_state and the node's own update are passed in.
    """
    if node_name == "safety_check":
        if update.get("crisis_detected"):
            return "crisis language detected - bypassing retrieval and generation"
        return "no crisis language detected"

    if node_name == "retrieve":
        return f"retrieved {len(update.get('documents', []))} chunks"

    if node_name == "grade_documents":
        before = len(prior_state.get("documents", []))
        after = len(update.get("documents", []))
        return f"{after} of {before} documents kept as relevant"

    if node_name == "transform_query":
        return f'query rewritten to: "{update.get("question", "")}"'

    if node_name == "generate":
        return "answer generated from retrieved documents"

    if node_name == "check_groundedness":
        if update.get("grounded"):
            return "answer is grounded in the retrieved documents"
        return "answer could not be fully verified against the retrieved documents"

    if node_name == "flag_ungrounded":
        return "added caveat: answer could not be fully verified"

    return "step complete"


def _build_done_payload(state: dict) -> dict:
    """Builds the final {answer, citations, disclaimer, retries_used} event."""
    generation = state.get("generation", "")
    answer = generation.replace(DISCLAIMER, "").rstrip()

    citations = [
        {
            "pmid": doc.metadata["pmid"],
            "title": doc.metadata["title"],
            "journal": doc.metadata["journal"],
            "year": doc.metadata["year"],
        }
        for doc in state.get("documents", [])
    ]

    return {
        "answer": answer,
        "citations": citations,
        "disclaimer": DISCLAIMER_TEXT,
        "retries_used": state.get("retry_count", 0),
    }


def _sse_event(event: str, data: dict) -> str:
    # json.dumps escapes any newlines inside the payload, so this is always
    # safe as a single SSE "data:" line even though answer/detail text can
    # itself contain newlines.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_graph_events(graph, question: str) -> AsyncIterator[str]:
    """Runs the graph via astream(), yielding one SSE event per completed node.

    astream() (rather than stream()) is used so LangGraph runs each node -
    including our synchronous, network-calling node functions - without
    blocking the FastAPI event loop between yields.
    """
    initial_state = {"question": question, "original_question": question, "retry_count": 0}
    accumulated_state = dict(initial_state)

    async for update in graph.astream(initial_state, stream_mode="updates"):
        for node_name, node_update in update.items():
            detail = _describe_node_update(node_name, accumulated_state, node_update)
            accumulated_state.update(node_update)
            yield _sse_event(
                "node_update",
                {"node": node_name, "status": "complete", "detail": detail},
            )

    yield _sse_event("done", _build_done_payload(accumulated_state))
