"""Request/response models for the /query endpoint."""

from __future__ import annotations

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class Source(BaseModel):
    number: int  # matches the [1]-style markers in the answer text
    pmid: str
    title: str
    journal: str
    year: str
    url: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[Source]
    crisis_detected: bool
    grounded: bool | None
    retry_count: int
