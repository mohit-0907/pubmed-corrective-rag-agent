"""Splits PubMed abstracts and PMC full text into chunks for embedding.

Two kinds of record flow through here, and they need different handling:

- **Abstract-only** (~74% of the corpus): a ~1,500-character abstract, which
  is one or two chunks. This is what the whole pipeline used to assume.
- **Full text** (~26%): ~38,000 characters of body across a dozen-plus
  sections, which is 25-30 chunks.

That asymmetry is the reason chunks carry their section label: a chunk from
"Results" should be distinguishable from one from "Methods", both to the
embedding model and to the generation prompt. It's also why retrieval caps
chunks-per-paper - without it, a single full-text paper outweighs a dozen
abstract-only ones purely on chunk count.
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from data_pipeline.pmc_client import clean_text, normalize_section_title

# Larger than the 800 used for abstract-only chunking: full-text paragraphs
# carry statistics and effect sizes that get mangled when split too finely.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150

# Sections shorter than this are stubs or stray headers - a 60-character
# "Primary outcome" chunk costs index space and never usefully matches.
MIN_SECTION_CHARS = 150

ABSTRACT_SECTION = "Abstract"


def _build_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_records(
    records: list[dict],
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[dict]:
    """Splits each record's abstract and full-text sections into chunks.

    Args:
        records: Dicts from the ingest step - pmid, title, journal, year,
            abstract, and optionally full_text_sections [{section, text}].
        chunk_size: Target characters per chunk.
        chunk_overlap: Characters shared between neighbouring chunks.

    Returns:
        A flat list of chunk dicts carrying the source record's citation
        metadata plus the section the text came from. The embedded text is
        prefixed with its section label so retrieval can distinguish
        "what did they find" from "how did they measure it".
    """
    splitter = _build_splitter(chunk_size, chunk_overlap)
    chunks: list[dict] = []

    for record in records:
        sections: list[dict] = [
            {"section": ABSTRACT_SECTION, "text": record["abstract"]},
            *record.get("full_text_sections", []),
        ]
        has_full_text = bool(record.get("full_text_sections"))
        chunk_index = 0

        for section in sections:
            text = section["text"]
            # Normalized here as well as at extraction, so a corpus ingested
            # before normalization existed doesn't need re-fetching.
            label = normalize_section_title(section["section"]) or "Body"
            # Both cleaners are idempotent, so re-applying them here is a
            # no-op on freshly extracted text while still repairing a corpus
            # ingested before they existed - no 10-minute re-fetch needed.
            text = clean_text(text)
            if label != ABSTRACT_SECTION and len(text) < MIN_SECTION_CHARS:
                continue

            for piece in splitter.split_text(text):
                chunks.append(
                    {
                        "pmid": record["pmid"],
                        "title": record["title"],
                        "journal": record["journal"],
                        "year": record["year"],
                        "section": label,
                        "has_full_text": has_full_text,
                        "chunk_index": chunk_index,
                        "text": f"[{label}] {piece}",
                    }
                )
                chunk_index += 1

    return chunks
