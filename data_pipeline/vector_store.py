"""Embeds chunks and persists them to a local Chroma vector store.

Kept separate from chunker.py: this is the boundary where we call out to
an embedding API and touch disk-persisted state, versus chunking which is
pure text transformation.
"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings

EMBEDDING_MODEL = "text-embedding-3-small"
PERSIST_DIRECTORY = "chroma_db"
COLLECTION_NAME = "pubmed_coping_strategies"


def build_vector_store(
    chunks: list[dict],
    persist_directory: str = PERSIST_DIRECTORY,
) -> Chroma:
    """Embeds chunks with OpenAI and writes them into a persisted Chroma collection.

    Args:
        chunks: Dicts from chunker.chunk_records, each with text, pmid,
            title, journal, year, and chunk_index.
        persist_directory: Directory Chroma should write its on-disk index to.

    Returns:
        The Chroma vector store, ready to query via similarity_search.
    """
    documents = [
        Document(
            page_content=chunk["text"],
            metadata={
                "pmid": chunk["pmid"],
                "title": chunk["title"],
                "journal": chunk["journal"],
                "year": chunk["year"],
                "chunk_index": chunk["chunk_index"],
            },
        )
        for chunk in chunks
    ]

    return Chroma.from_documents(
        documents=documents,
        embedding=OpenAIEmbeddings(model=EMBEDDING_MODEL),
        collection_name=COLLECTION_NAME,
        persist_directory=persist_directory,
    )


def load_vector_store(persist_directory: str = PERSIST_DIRECTORY) -> Chroma:
    """Loads the previously persisted Chroma collection without re-embedding."""
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=OpenAIEmbeddings(model=EMBEDDING_MODEL),
        persist_directory=persist_directory,
    )
