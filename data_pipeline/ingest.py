"""Fetches the full corpus from PubMed and persists it to disk as JSON.

Separate from run_sample_fetch.py (which is a print-and-eyeball sanity
check): this is the actual ingestion step whose output downstream chunking
and embedding steps read from, so the corpus doesn't need to be re-fetched
from NCBI every time we iterate on chunking/embedding logic.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from data_pipeline.pubmed_client import fetch_pubmed_records

SEARCH_QUERY = (
    '("Adaptation, Psychological"[MeSH] OR "coping"[tiab]) '
    'AND ("Depression"[MeSH] OR "Anxiety"[MeSH] OR "stress, psychological"[MeSH]) '
    'AND ("Cognitive Behavioral Therapy"[MeSH] OR "Mindfulness"[MeSH] OR "self-care"[tiab])'
)

MAX_RESULTS = 2000
OUTPUT_PATH = Path("data/raw/pubmed_abstracts.json")


def main() -> None:
    load_dotenv()

    records = fetch_pubmed_records(SEARCH_QUERY, max_results=MAX_RESULTS)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")

    print(f"Saved {len(records)} records to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
