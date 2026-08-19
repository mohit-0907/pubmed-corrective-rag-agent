"""Assembles the LangGraph state machine.

  [safety guardrail] -> retrieve -> grade_documents -> [generate | transform_query loop]
  -> generate -> check_groundedness -> [END | generate loop | transform_query loop]
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    check_groundedness,
    flag_ungrounded,
    generate,
    grade_documents,
    retrieve,
    safety_check,
    transform_query,
)
from agent.routing import (
    decide_to_generate,
    route_after_groundedness_check,
    route_after_safety_check,
)
from agent.state import GraphState


def build_graph():
    """Builds and compiles the corrective RAG graph."""
    workflow = StateGraph(GraphState)

    workflow.add_node("safety_check", safety_check)
    workflow.add_node("retrieve", retrieve)
    workflow.add_node("grade_documents", grade_documents)
    workflow.add_node("transform_query", transform_query)
    workflow.add_node("generate", generate)
    workflow.add_node("check_groundedness", check_groundedness)
    workflow.add_node("flag_ungrounded", flag_ungrounded)

    workflow.add_edge(START, "safety_check")
    workflow.add_conditional_edges(
        "safety_check",
        route_after_safety_check,
        {"retrieve": "retrieve", END: END},
    )
    workflow.add_edge("retrieve", "grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {"generate": "generate", "transform_query": "transform_query"},
    )
    workflow.add_edge("transform_query", "retrieve")
    workflow.add_edge("generate", "check_groundedness")
    workflow.add_conditional_edges(
        "check_groundedness",
        route_after_groundedness_check,
        {
            "generate": "generate",
            "transform_query": "transform_query",
            "flag_ungrounded": "flag_ungrounded",
            END: END,
        },
    )
    workflow.add_edge("flag_ungrounded", END)

    return workflow.compile()
