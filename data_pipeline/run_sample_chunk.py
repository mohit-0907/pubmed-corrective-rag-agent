"""Manual sanity-check script: chunk the persisted corpus and print stats.

Not a test - this is for eyeballing how the corpus splits before paying to
embed it, and specifically for watching the abstract-only vs full-text
asymmetry, since that's what drives both index size and retrieval balance.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

from data_pipeline.chunker import chunk_records

CORPUS_PATH = Path("data/raw/pubmed_corpus.json")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    records = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    chunks = chunk_records(records)

    full_text_records = [r for r in records if r.get("full_text_sections")]
    per_paper = Counter(chunk["pmid"] for chunk in chunks)
    full_pmids = {r["pmid"] for r in full_text_records}

    full_counts = [n for pmid, n in per_paper.items() if pmid in full_pmids]
    abstract_counts = [n for pmid, n in per_paper.items() if pmid not in full_pmids]

    print(f"{len(records):,} records -> {len(chunks):,} chunks")
    print(f"  with full text:  {len(full_text_records):,} records "
          f"({100 * len(full_text_records) / len(records):.0f}%)")
    print(f"  abstract only:   {len(records) - len(full_text_records):,} records\n")

    if full_counts:
        print(f"  chunks per full-text paper:  mean {statistics.mean(full_counts):5.1f}  "
              f"max {max(full_counts)}")
    if abstract_counts:
        print(f"  chunks per abstract-only:    mean {statistics.mean(abstract_counts):5.1f}  "
              f"max {max(abstract_counts)}")
    if full_counts and abstract_counts:
        ratio = statistics.mean(full_counts) / statistics.mean(abstract_counts)
        print(f"\n  -> a full-text paper has {ratio:.0f}x more chunks than an abstract-only one,")
        print("     which is why retrieval needs a per-paper cap or it will be dominated by them.")

    lengths = [len(chunk["text"]) for chunk in chunks]
    print(f"\n  chunk chars: mean {statistics.mean(lengths):.0f}, "
          f"median {statistics.median(lengths):.0f}, max {max(lengths)}")

    print("\nMost common sections:")
    for section, count in Counter(c["section"] for c in chunks).most_common(12):
        print(f"  {count:>6,}  {section[:60]}")


if __name__ == "__main__":
    main()
