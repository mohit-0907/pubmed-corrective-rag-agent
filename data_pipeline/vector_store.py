"""Embeds chunks and persists them to a Pinecone serverless index.

Hosted rather than local because the corpus outgrew what can live in the
repo: 20,893 chunks of abstracts + PMC full text come to ~315 MB on disk,
of which the Chroma sqlite file alone is ~187 MB - well past GitHub's
100 MB per-file limit, and not closable by shrinking chunks or truncating
embeddings without degrading retrieval on both axes at once.

`dimensions` is still exposed because text-embedding-3 models support
Matryoshka truncation; it now trades index cost rather than repo size.
"""

from __future__ import annotations

import os
import time

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS: int | None = None  # None = the model's native 1536
NATIVE_DIMENSIONS = 1536

INDEX_NAME = "pubmed-coping-strategies"
# Pinecone's free tier only provisions serverless indexes in this region.
CLOUD = "aws"
REGION = "us-east-1"


def _embeddings(dimensions: int | None) -> OpenAIEmbeddings:
    """Builds the embedding client, optionally truncating the vector width."""
    if dimensions:
        return OpenAIEmbeddings(model=EMBEDDING_MODEL, dimensions=dimensions)
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def _client() -> Pinecone:
    """Returns a Pinecone client, failing loudly if the key isn't configured."""
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "PINECONE_API_KEY is not set. Add it to .env (local) or the service "
            "environment (deployed) - see .env.example."
        )
    return Pinecone(api_key=api_key)


def ensure_index(
    index_name: str = INDEX_NAME,
    dimensions: int | None = EMBEDDING_DIMENSIONS,
) -> None:
    """Creates the serverless index if it doesn't already exist.

    Waits for it to report ready, since Pinecone returns from create_index
    before the index will accept upserts.
    """
    client = _client()
    existing = {index["name"] for index in client.list_indexes()}
    if index_name in existing:
        return

    client.create_index(
        name=index_name,
        dimension=dimensions or NATIVE_DIMENSIONS,
        metric="cosine",
        spec=ServerlessSpec(cloud=CLOUD, region=REGION),
    )

    while not client.describe_index(index_name).status["ready"]:
        time.sleep(1)


def _to_documents(chunks: list[dict]) -> list[Document]:
    """Converts chunk dicts to LangChain Documents.

    Pinecone metadata values must be strings, numbers, booleans, or lists of
    strings - so everything here stays primitive, same constraint Chroma had.
    """
    return [
        Document(
            page_content=chunk["text"],
            metadata={
                "pmid": chunk["pmid"],
                "title": chunk["title"],
                "journal": chunk["journal"],
                "year": chunk["year"],
                "section": chunk["section"],
                "has_full_text": chunk["has_full_text"],
                "chunk_index": chunk["chunk_index"],
            },
        )
        for chunk in chunks
    ]


def build_vector_store(
    chunks: list[dict],
    index_name: str = INDEX_NAME,
    dimensions: int | None = EMBEDDING_DIMENSIONS,
    batch_size: int = 200,
) -> PineconeVectorStore:
    """Embeds chunks and upserts them into the Pinecone index.

    Args:
        chunks: Dicts from chunker.chunk_records.
        index_name: Pinecone index to write into; created if absent.
        dimensions: Optional embedding width; None uses the model default.
        batch_size: Documents per upsert request.

    Returns:
        The vector store, ready to query via similarity_search.
    """
    ensure_index(index_name, dimensions)

    store = PineconeVectorStore(
        index=_client().Index(index_name),
        embedding=_embeddings(dimensions),
    )

    documents = _to_documents(chunks)
    for start in range(0, len(documents), batch_size):
        store.add_documents(documents[start : start + batch_size])
        print(f"  upserted {min(start + batch_size, len(documents)):,}/{len(documents):,}",
              end="\r", flush=True)
    print()

    return store


def load_vector_store(
    index_name: str = INDEX_NAME,
    dimensions: int | None = EMBEDDING_DIMENSIONS,
) -> PineconeVectorStore:
    """Connects to the existing Pinecone index without re-embedding."""
    return PineconeVectorStore(
        index=_client().Index(index_name),
        embedding=_embeddings(dimensions),
    )
