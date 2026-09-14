"""Chunks the persisted corpus and embeds it into the Pinecone index.

Reads data/raw/pubmed_corpus.json (written by ingest.py) rather than
re-fetching from NCBI, so re-running the embedding step doesn't re-hit the
API or burn PMC full-text calls on a corpus we already have.

Chunk size and embedding width stay CLI-configurable: they set how many
vectors the index holds, which is the main cost lever now that storage is
hosted rather than committed to the repo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from data_pipeline.chunker import CHUNK_OVERLAP, CHUNK_SIZE, chunk_records
from data_pipeline.vector_store import INDEX_NAME, _client, build_vector_store

CORPUS_PATH = Path("data/raw/pubmed_corpus.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE)
    parser.add_argument("--chunk-overlap", type=int, default=CHUNK_OVERLAP)
    parser.add_argument("--dimensions", type=int, default=None,
                        help="Embedding width; omit for the model's native 1536.")
    parser.add_argument("--index-name", default=INDEX_NAME)
    args = parser.parse_args()

    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")

    records = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    with_full_text = sum(1 for r in records if r.get("full_text_sections"))
    chunks = chunk_records(records, args.chunk_size, args.chunk_overlap)

    print(f"{len(records):,} records ({with_full_text} with full text) "
          f"-> {len(chunks):,} chunks at {args.chunk_size} chars")
    print(f"Embedding at {args.dimensions or 1536} dimensions "
          f"into Pinecone index '{args.index_name}' ...")

    build_vector_store(chunks, index_name=args.index_name, dimensions=args.dimensions)

    stats = _client().Index(args.index_name).describe_index_stats()
    print(f"\nIndex '{args.index_name}' now holds {stats.get('total_vector_count', 0):,} vectors")


if __name__ == "__main__":
    main()
