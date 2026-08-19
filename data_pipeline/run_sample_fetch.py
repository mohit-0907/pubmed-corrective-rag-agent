"""Manual sanity-check script: fetch a small sample from PubMed and print it.

Not a test - this is for eyeballing data quality (abstract completeness,
year/journal parsing) before scaling up to full ingestion + chunking.
"""

from __future__ import annotations

import sys

from dotenv import load_dotenv

from data_pipeline.pubmed_client import fetch_pubmed_records

SEARCH_QUERY = (
    '("Adaptation, Psychological"[MeSH] OR "coping"[tiab]) '
    'AND ("Depression"[MeSH] OR "Anxiety"[MeSH] OR "stress, psychological"[MeSH]) '
    'AND ("Cognitive Behavioral Therapy"[MeSH] OR "Mindfulness"[MeSH] OR "self-care"[tiab])'
)


def main() -> None:
    load_dotenv()
    # Windows terminals often default stdout to cp1252, which can't encode
    # some characters PubMed abstracts contain (e.g. thin spaces, en dashes).
    sys.stdout.reconfigure(encoding="utf-8")

    records = fetch_pubmed_records(SEARCH_QUERY, max_results=20)
    print(f"\nFetched {len(records)} records with abstracts\n{'=' * 60}")

    for record in records:
        print(f"PMID:    {record['pmid']}")
        print(f"Title:   {record['title']}")
        print(f"Journal: {record['journal']} ({record['year']})")
        print(f"Abstract: {record['abstract'][:300]}...")
        print("-" * 60)


if __name__ == "__main__":
    main()
