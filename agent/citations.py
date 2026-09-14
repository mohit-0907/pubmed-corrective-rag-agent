"""Assigns stable citation numbers to retrieved documents.

The generation prompt and the API response have to agree on which paper is
[1], so numbering happens in one place and both sides read from it. Letting
the model invent its own numbering would leave markers that don't line up
with the source list the reader sees.

Numbering is per *paper*, not per chunk: retrieval can return two chunks
from the same article, and those should share one citation number rather
than appear as two separate sources.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document

PUBMED_URL = "https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def number_sources(documents: list[Document]) -> list[dict]:
    """Returns one numbered entry per unique paper, in first-appearance order.

    First appearance is relevance order, since retrieval hands documents over
    already ranked - so [1] is the best-matching source.
    """
    sources: list[dict] = []
    seen: set[str] = set()

    for document in documents:
        meta = document.metadata
        pmid = meta.get("pmid", "")
        if not pmid or pmid in seen:
            continue
        seen.add(pmid)
        sources.append(
            {
                "number": len(sources) + 1,
                "pmid": pmid,
                "title": meta.get("title", ""),
                "journal": meta.get("journal", ""),
                "year": meta.get("year", ""),
                "url": PUBMED_URL.format(pmid=pmid),
            }
        )

    return sources


def citation_numbers_by_pmid(sources: list[dict]) -> dict[str, int]:
    """Maps PMID -> citation number, for labelling chunks in the prompt."""
    return {source["pmid"]: source["number"] for source in sources}


def cited_sources(sources: list[dict], answer: str) -> list[dict]:
    """Narrows a source list to the ones the answer actually cites.

    Retrieval and grading keep more sources than the answer ends up using, and
    listing an uncited [4] under "Sources" leaves the reader hunting the text
    for a marker that was never written. Original numbers are preserved rather
    than compacted, so every marker in the text still resolves - the list may
    read 1, 2, 5 with gaps, which is the honest shape.
    """
    referenced = {int(match) for match in re.findall(r"\[(\d+)\]", answer)}
    if not referenced:
        return []
    return [source for source in sources if source["number"] in referenced]
