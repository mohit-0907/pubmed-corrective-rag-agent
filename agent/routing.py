"""Conditional-edge decision functions for the correction loop.

Kept separate from nodes.py: these don't mutate GraphState, they just read
it and return the name of the next node (LangGraph's contract for
conditional edges), so mixing them into nodes.py would blur two different
function shapes together.
"""

from __future__ import annotations

from langgraph.graph import END

from agent.graders import grade_answer
from agent.state import GraphState

# Shared cap on correction-loop iterations, checked before either looping
# back to retrieval (transform_query) or regenerating (generate). Keeps a
# single retry_count meaningful as "total correction attempts made" per the
# state schema, and guarantees the graph terminates.
MAX_RETRIES = 2


def route_after_safety_check(state: GraphState) -> str:
    """Routes after safety_check: bypass the RAG pipeline entirely, or proceed."""
    if state["crisis_detected"]:
        return END
    return "retrieve"


def decide_to_generate(state: GraphState) -> str:
    """Routes after grade_documents: proceed to generate, or retry retrieval."""
    if state["documents"]:
        return "generate"
    if state["retry_count"] < MAX_RETRIES:
        return "transform_query"
    # Out of retries with nothing relevant - let generate say so explicitly
    # (the system prompt already instructs it to admit insufficient evidence)
    # rather than looping forever.
    return "generate"


def route_after_groundedness_check(state: GraphState) -> str:
    """Routes after check_groundedness: END, regenerate, or retry retrieval."""
    if not state["grounded"]:
        if state["retry_count"] < MAX_RETRIES:
            return "generate"
        return "flag_ungrounded"

    if grade_answer(state["original_question"], state["generation"]):
        return END

    if state["retry_count"] < MAX_RETRIES:
        return "transform_query"
    return END
