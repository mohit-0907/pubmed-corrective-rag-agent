"""The original Week 2 linear graph: retrieve -> generate, no correction loop.

Kept as the eval baseline - "what plain RAG produces on the same corpus" -
so the corrective loop's contribution can be measured rather than asserted.

Deliberately missing three things the corrective graph has, because their
absence is exactly what the comparison is meant to expose: no safety_check
(so a crisis question goes straight into retrieval), no relevance grading or
retry loop, and no plain-language rewrite.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.nodes import DISCLAIMER, generate, retrieve
from agent.state import GraphState


def use_draft_as_answer(state: GraphState) -> dict:
    """Promotes the technical draft to the final answer.

    The corrective graph's simplify node normally does this (rewriting as it
    goes). The baseline has no rewrite step, so the draft is the answer -
    which is the point: it shows what the reader would have gotten without it.
    """
    return {"generation": state["draft_generation"] + DISCLAIMER}


def build_linear_graph():
    """Builds and compiles the linear (non-corrective) retrieve -> generate graph."""
    workflow = StateGraph(GraphState)

    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)
    workflow.add_node("use_draft_as_answer", use_draft_as_answer)

    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", "use_draft_as_answer")
    workflow.add_edge("use_draft_as_answer", END)

    return workflow.compile()
