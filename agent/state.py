"""Shared state schema passed between LangGraph nodes."""

from __future__ import annotations

from typing import TypedDict

from langchain_core.documents import Document


class GraphState(TypedDict):
    question: str
    original_question: str
    documents: list[Document]
    generation: str
    retry_count: int
    grounded: bool
    crisis_detected: bool
