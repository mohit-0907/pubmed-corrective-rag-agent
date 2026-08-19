"""Chunks the persisted corpus and embeds it into the Chroma vector store.

Reads data/raw/pubmed_abstracts.json (written by ingest.py) rather than
re-fetching from PubMed, so re-running the embedding step doesn't re-hit
NCBI or burn OpenAI calls on a re-ingest of the same data.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from data_pipeline.chunker import chunk_records
from data_pipeline.vector_store import build_vector_store

CORPUS_PATH = Path("data/raw/pubmed_abstracts.json")


def main() -> None:
    load_dotenv()

    records = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    chunks = chunk_records(records)

    build_vector_store(chunks)
    print(f"Embedded {len(chunks)} chunks from {len(records)} abstracts into Chroma")


if __name__ == "__main__":
    main()
