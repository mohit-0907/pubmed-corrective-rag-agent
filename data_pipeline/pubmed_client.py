"""Client for pulling abstracts + metadata from the PubMed E-utilities API.

Two-step E-utilities flow: esearch resolves a query to a list of PMIDs,
then efetch pulls the full XML record (title/abstract/journal/year) for
those PMIDs. Kept as a standalone module (no LangChain deps) since this
is the boundary where we talk to an external, rate-limited API.
"""

from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET

import requests

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ESEARCH_URL = f"{EUTILS_BASE}/esearch.fcgi"
EFETCH_URL = f"{EUTILS_BASE}/efetch.fcgi"

# NCBI allows 3 req/sec without an API key, 10 req/sec with one.
# We pad slightly below those ceilings to stay safely under the limit.
_NO_KEY_DELAY_SECONDS = 0.34
_WITH_KEY_DELAY_SECONDS = 0.11

# efetch can technically take thousands of IDs per call, but NCBI asks
# large jobs to be chunked; 200 is a conservative, well-documented batch size.
_EFETCH_BATCH_SIZE = 200


def _rate_limit_delay(api_key: str | None) -> float:
    """Returns the sleep interval to use between E-utilities calls."""
    return _WITH_KEY_DELAY_SECONDS if api_key else _NO_KEY_DELAY_SECONDS


def _esearch_pmids(query: str, max_results: int, api_key: str | None) -> list[str]:
    """Resolves a PubMed query string to a list of matching PMIDs."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key

    response = requests.get(ESEARCH_URL, params=params, timeout=30)
    response.raise_for_status()
    time.sleep(_rate_limit_delay(api_key))

    return response.json().get("esearchresult", {}).get("idlist", [])


def _text_or_none(node: ET.Element | None) -> str | None:
    """Extracts stripped text from an XML element, tolerating None/empty nodes."""
    if node is None or node.text is None:
        return None
    text = node.text.strip()
    return text or None


def _parse_abstract(article: ET.Element) -> str | None:
    """Joins all AbstractText sections into one string.

    Structured abstracts (e.g. "BACKGROUND: ... METHODS: ...") split each
    section into its own AbstractText node with a Label attribute, so we
    prefix each section with its label when present.
    """
    abstract_node = article.find("Abstract")
    if abstract_node is None:
        return None

    sections = []
    for section in abstract_node.findall("AbstractText"):
        text = _text_or_none(section)
        if text is None:
            continue
        label = section.get("Label")
        sections.append(f"{label}: {text}" if label else text)

    return " ".join(sections) if sections else None


def _parse_year(article: ET.Element) -> str | None:
    """Extracts publication year, falling back to MedlineDate for records
    that only carry a free-text date (e.g. "2020 Winter")."""
    pub_date = article.find("Journal/JournalIssue/PubDate")
    if pub_date is None:
        return None

    year = _text_or_none(pub_date.find("Year"))
    if year:
        return year

    medline_date = _text_or_none(pub_date.find("MedlineDate"))
    if medline_date:
        # MedlineDate free text usually starts with a 4-digit year, e.g. "2020 Winter".
        return medline_date[:4]

    return None


def _parse_pubmed_article(pubmed_article: ET.Element) -> dict | None:
    """Parses a single <PubmedArticle> element into our record shape.

    Returns None (rather than raising) when required fields are missing,
    so one malformed/incomplete record doesn't crash the whole batch.
    """
    citation = pubmed_article.find("MedlineCitation")
    if citation is None:
        return None

    pmid = _text_or_none(citation.find("PMID"))
    article = citation.find("Article")
    if pmid is None or article is None:
        return None

    title = _text_or_none(article.find("ArticleTitle"))
    abstract = _parse_abstract(article)
    if abstract is None:
        # No abstract text (e.g. letters, editorials) - not useful for a RAG
        # corpus built on findings, so we flag and skip rather than crash.
        print(f"[pubmed_client] Skipping PMID {pmid}: no abstract available")
        return None

    journal = _text_or_none(article.find("Journal/Title")) or _text_or_none(
        article.find("Journal/ISOAbbreviation")
    )
    year = _parse_year(article)

    return {
        "pmid": pmid,
        "title": title or "",
        "abstract": abstract,
        "journal": journal or "",
        "year": year or "",
    }


def _efetch_records(pmids: list[str], api_key: str | None) -> list[dict]:
    """Fetches and parses full records for a list of PMIDs, batching requests."""
    records: list[dict] = []

    for batch_start in range(0, len(pmids), _EFETCH_BATCH_SIZE):
        batch = pmids[batch_start : batch_start + _EFETCH_BATCH_SIZE]
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "abstract",
            "retmode": "xml",
        }
        if api_key:
            params["api_key"] = api_key

        response = requests.get(EFETCH_URL, params=params, timeout=60)
        response.raise_for_status()
        time.sleep(_rate_limit_delay(api_key))

        root = ET.fromstring(response.content)
        for pubmed_article in root.findall("PubmedArticle"):
            record = _parse_pubmed_article(pubmed_article)
            if record is not None:
                records.append(record)

    return records


def fetch_pubmed_records(
    query: str,
    max_results: int = 20,
    api_key: str | None = None,
) -> list[dict]:
    """Searches PubMed and returns parsed records for the matching articles.

    Runs esearch (query -> PMIDs) then efetch (PMIDs -> full XML records),
    skipping any records with no abstract. Pass api_key (or set NCBI_API_KEY
    in the environment) to raise the rate limit from 3 to 10 req/sec.

    Args:
        query: A PubMed search query, e.g. using MeSH/tiab field tags.
        max_results: Maximum number of PMIDs to resolve via esearch.
        api_key: Optional NCBI API key; falls back to the NCBI_API_KEY env var.

    Returns:
        A list of dicts with keys: pmid, title, abstract, journal, year.
    """
    api_key = api_key or os.getenv("NCBI_API_KEY")

    pmids = _esearch_pmids(query, max_results, api_key)
    if not pmids:
        return []

    return _efetch_records(pmids, api_key)
