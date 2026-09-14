"""Fetches the corpus from PubMed, enriched with PMC full text where available.

Two passes:

1. PubMed esearch/efetch for abstracts + metadata. The XML already carries a
   PMCID for articles deposited in PubMed Central, so that comes free.
2. For English articles that have a PMCID, a PMC efetch for the full body.

Only ~26% of the corpus clears both gates (a PMCID exists, and PMC actually
serves a body for it), so most records stay abstract-only. That's expected -
the point is that the quarter which does resolve carries ~25x more text.

Output feeds build_index.py, so the corpus isn't re-fetched every time
chunking or embedding logic changes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from data_pipeline.pmc_client import fetch_full_text
from data_pipeline.pubmed_client import fetch_pubmed_records

SEARCH_QUERY = (
    '("Adaptation, Psychological"[MeSH] OR "coping"[tiab]) '
    'AND ("Depression"[MeSH] OR "Anxiety"[MeSH] OR "stress, psychological"[MeSH]) '
    'AND ("Cognitive Behavioral Therapy"[MeSH] OR "Mindfulness"[MeSH] OR "self-care"[tiab])'
)

MAX_RESULTS = 2000
OUTPUT_PATH = Path("data/raw/pubmed_corpus.json")


def enrich_with_full_text(records: list[dict], api_key: str | None) -> list[dict]:
    """Attaches PMC full-text sections to records that have retrievable ones.

    Failures are per-record and non-fatal: one article whose XML won't parse
    shouldn't cost us the other 1,800.
    """
    candidates = [r for r in records if r["pmcid"] and r["language"] == "eng"]
    print(f"{len(candidates)}/{len(records)} records are English with a PMCID")

    resolved = 0
    for i, record in enumerate(candidates, 1):
        try:
            sections = fetch_full_text(record["pmcid"], api_key=api_key)
        except Exception as exc:  # noqa: BLE001 - one bad article shouldn't abort ingestion
            print(f"\n  {record['pmcid']}: {type(exc).__name__}: {exc}")
            sections = []

        if sections:
            record["full_text_sections"] = sections
            resolved += 1

        print(f"  full text {i}/{len(candidates)} (resolved {resolved})", end="\r")
        sys.stdout.flush()

    print(f"\nFull text retrieved for {resolved}/{len(records)} records "
          f"({100 * resolved / max(len(records), 1):.0f}% of corpus)")
    return records


def main() -> None:
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")
    api_key = os.getenv("NCBI_API_KEY")

    records = fetch_pubmed_records(SEARCH_QUERY, max_results=MAX_RESULTS, api_key=api_key)
    print(f"Fetched {len(records)} records with abstracts")

    records = enrich_with_full_text(records, api_key)

    body_chars = sum(
        len(s["text"]) for r in records for s in r.get("full_text_sections", [])
    )
    abstract_chars = sum(len(r["abstract"]) for r in records)
    print(f"Corpus text: {abstract_chars:,} abstract chars + {body_chars:,} body chars")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(records, indent=2), encoding="utf-8")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
