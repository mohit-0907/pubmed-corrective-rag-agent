"""Manual sanity-check script: chunk the persisted corpus and print stats.

Not a test - this is for eyeballing chunk-size distribution and a couple
of example splits before wiring chunks into embedding.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from data_pipeline.chunker import chunk_records

CORPUS_PATH = Path("data/raw/pubmed_abstracts.json")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    records = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    chunks = chunk_records(records)

    multi_chunk_abstracts = sum(
        1 for r in records if sum(1 for c in chunks if c["pmid"] == r["pmid"]) > 1
    )

    print(f"{len(records)} abstracts -> {len(chunks)} chunks")
    print(f"Abstracts split into >1 chunk: {multi_chunk_abstracts}")
    print(f"Avg chunks/abstract: {len(chunks) / len(records):.2f}\n")

    # Show one abstract that got split, so overlap/boundaries can be checked by eye.
    split_pmids = {c["pmid"] for c in chunks if c["chunk_index"] == 1}
    example_pmid = next(iter(split_pmids))
    example_chunks = [c for c in chunks if c["pmid"] == example_pmid]

    print(f"Example split (PMID {example_pmid}, {len(example_chunks)} chunks):")
    print("=" * 60)
    for chunk in example_chunks:
        print(f"--- chunk {chunk['chunk_index']} ({len(chunk['text'])} chars) ---")
        print(chunk["text"])
        print()


if __name__ == "__main__":
    main()
