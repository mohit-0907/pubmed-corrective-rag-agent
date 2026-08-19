"""Splits PubMed abstracts into chunks for embedding.

Most abstracts are short enough to embed as a single chunk, but structured
abstracts (BACKGROUND/METHODS/RESULTS/CONCLUSIONS, common in trial reports)
can run long enough that splitting improves retrieval precision - a query
about "sample size" shouldn't have to match against the whole abstract
when only the METHODS section is relevant. We still keep every chunk tied
back to its source record's metadata for citations.
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

# Sized around typical abstract length: short/unstructured abstracts stay
# a single chunk, longer structured ones split into 2-3 overlapping pieces.
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
)


def chunk_records(records: list[dict]) -> list[dict]:
    """Splits each record's abstract into overlapping text chunks.

    Args:
        records: Dicts with at least pmid, title, abstract, journal, year
            (the shape returned by pubmed_client.fetch_pubmed_records).

    Returns:
        A flat list of dicts, one per chunk, each carrying the chunk text
        plus the source record's metadata (pmid, title, journal, year) and
        its index among that abstract's chunks, so citations and later
        re-assembly stay possible.
    """
    chunks: list[dict] = []

    for record in records:
        for chunk_index, chunk_text in enumerate(_splitter.split_text(record["abstract"])):
            chunks.append(
                {
                    "pmid": record["pmid"],
                    "title": record["title"],
                    "journal": record["journal"],
                    "year": record["year"],
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                }
            )

    return chunks
