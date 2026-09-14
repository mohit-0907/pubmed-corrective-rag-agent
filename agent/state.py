"""Shared state schema passed between LangGraph nodes."""

from __future__ import annotations

from typing import TypedDict

from langchain_core.documents import Document


class GraphState(TypedDict):
    question: str
    original_question: str
    documents: list[Document]
    draft_generation: str  # technical synthesis, before plain-language rewrite
    generation: str        # what the reader actually sees
    retry_count: int
    grounded: bool
    crisis_detected: bool
