"""LLM-based graders and query rewriter used by the correction loop.

Split out from nodes.py because these are pure classification/rewrite
calls with no state-mutation logic of their own - nodes.py wires their
outputs into GraphState updates.

Chains are built lazily (on first call, not at import time) so importing
this module doesn't require OPENAI_API_KEY to already be loaded into the
environment - callers load .env in their own entry point before anything
runs, and eagerly building a ChatOpenAI client at import time would race
against that.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# Grading/rewriting are simple, high-volume classification calls (once per
# retrieved chunk, plus once or twice per correction-loop iteration) rather
# than the open-ended synthesis generate() does, so a cheaper/faster model
# is a reasonable fit here independent of which model does generation.
GRADER_MODEL = "gpt-4o-mini"


@lru_cache(maxsize=1)
def _grader_llm() -> ChatOpenAI:
    return ChatOpenAI(model=GRADER_MODEL, temperature=0)


class DocumentRelevance(BaseModel):
    binary_score: Literal["yes", "no"] = Field(
        description="'yes' if the document is relevant to the question, else 'no'"
    )


class HallucinationGrade(BaseModel):
    binary_score: Literal["yes", "no"] = Field(
        description="'yes' if the answer is grounded in / supported by the given facts, else 'no'"
    )


class AnswerGrade(BaseModel):
    binary_score: Literal["yes", "no"] = Field(
        description="'yes' if the answer actually addresses the question, else 'no'"
    )


@lru_cache(maxsize=1)
def _document_grader_chain():
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a grader assessing the relevance of a retrieved biomedical "
                    "abstract excerpt to a user question. Give a binary score 'yes' or "
                    "'no'. 'yes' means the excerpt contains information that would help "
                    "answer the question."
                ),
            ),
            ("human", "Retrieved excerpt:\n\n{document}\n\nUser question: {question}"),
        ]
    )
    return prompt | _grader_llm().with_structured_output(DocumentRelevance)


@lru_cache(maxsize=1)
def _hallucination_grader_chain():
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a grader assessing whether an answer is grounded in a set "
                    "of retrieved facts. Give a binary score 'yes' or 'no'. 'yes' means "
                    "every claim in the answer is supported by the facts, with nothing "
                    "invented."
                ),
            ),
            ("human", "Facts:\n\n{documents}\n\nAnswer:\n\n{generation}"),
        ]
    )
    return prompt | _grader_llm().with_structured_output(HallucinationGrade)


@lru_cache(maxsize=1)
def _answer_grader_chain():
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are a grader assessing whether an answer actually addresses a "
                    "user's question (as opposed to being grounded but off-topic or "
                    "evasive). Give a binary score 'yes' or 'no'."
                ),
            ),
            ("human", "Question:\n\n{question}\n\nAnswer:\n\n{generation}"),
        ]
    )
    return prompt | _grader_llm().with_structured_output(AnswerGrade)


@lru_cache(maxsize=1)
def _query_rewrite_chain():
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You rewrite user questions into queries optimized for vector "
                    "similarity search over biomedical research abstracts. Preserve the "
                    "core clinical/psychological intent. Return ONLY the rewritten query, "
                    "no explanation."
                ),
            ),
            ("human", "{question}"),
        ]
    )
    return prompt | _grader_llm()


def grade_document_relevance(document: str, question: str) -> bool:
    """True if the document excerpt is relevant to the question."""
    result = _document_grader_chain().invoke({"document": document, "question": question})
    return result.binary_score == "yes"


def grade_hallucination(documents: str, generation: str) -> bool:
    """True if every claim in the generation is supported by the documents."""
    result = _hallucination_grader_chain().invoke(
        {"documents": documents, "generation": generation}
    )
    return result.binary_score == "yes"


def grade_answer(question: str, generation: str) -> bool:
    """True if the generation actually addresses the question."""
    result = _answer_grader_chain().invoke({"question": question, "generation": generation})
    return result.binary_score == "yes"


def rewrite_query(question: str) -> str:
    """Rewrites a question into a retrieval-friendlier search query."""
    response = _query_rewrite_chain().invoke({"question": question})
    return response.content.strip()
