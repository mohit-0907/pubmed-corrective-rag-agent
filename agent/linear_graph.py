"""The original Week 2 linear graph: retrieve -> generate, no correction loop.

Reconstructed for eval comparison purposes (see eval/run_eval.py) - it was
overwritten in place when the corrective graph replaced it in agent/graph.py
and no earlier commit exists to restore it from. Reuses retrieve and
generate from agent/nodes.py completely unchanged, so this file is purely
additive graph wiring, not a second implementation of those nodes.

Deliberately has no safety_check node: the guardrail didn't exist yet at
this stage of the project, and that absence is itself part of what the
eval comparison is meant to show.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.nodes import generate, retrieve
from agent.state import GraphState


def build_linear_graph():
    """Builds and compiles the linear (non-corrective) retrieve -> generate graph."""
    workflow = StateGraph(GraphState)

    workflow.add_node("retrieve", retrieve)
    workflow.add_node("generate", generate)

    workflow.add_edge(START, "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", END)

    return workflow.compile()
