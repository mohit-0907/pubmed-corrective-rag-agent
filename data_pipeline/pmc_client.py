"""Client for pulling full-text articles from PubMed Central (PMC).

Only ~26% of our PubMed corpus has retrievable full text - a paper needs a
PMCID *and* has to be in a deposit whose body PMC will serve via efetch.
When full text is available it's worth a lot: measured across a 40-paper
sample it averages ~38,500 characters against ~1,500 for the abstract.

The parsing target is JATS XML, whose shape is:

    <article>
      <front>  ... metadata + abstract (we already have these from PubMed)
      <body>   ... <sec> trees holding the actual article text  <- what we want
      <back>   ... references, funding, acknowledgements        <- ~29% of the
                                                                   article, all
                                                                   noise for RAG
"""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET

import requests

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

_NO_KEY_DELAY_SECONDS = 0.34
_WITH_KEY_DELAY_SECONDS = 0.11

# Inline elements whose *text* we drop but whose tail we keep, so a sentence
# survives intact when a citation marker is removed from the middle of it.
# <xref> matters most: it renders as "[12,13]", which is both noise and a
# collision risk with the [1]-style citation markers we generate ourselves.
_SKIP_SUBTREE_TAGS = {
    "xref",
    "table-wrap",
    "fig",
    "graphic",
    "media",
    "disp-formula",
    "inline-formula",
    "supplementary-material",
    "ext-link",
}

# Sections dropped by title. A denylist (rather than an allowlist of
# "results/methods/...") because real section titles vary far more than the
# IMRaD ideal - a sample of 34 papers included "measures", "randomization",
# "data collection" and "procedures", all of which are study design worth
# keeping and none of which an allowlist would have anticipated.
_DROP_SECTION_PATTERNS = (
    "introduction",
    "background",
    "ethic",
    "consent",
    "acknowledg",
    "funding",
    "competing interest",
    "conflict of interest",
    "author contribution",
    "data availability",
    "availability of data",
    "supplementary",
    "additional file",
    "publisher's note",
    "abbreviation",
    "references",
    "disclosure",
)

MIN_BODY_CHARS = 500

# PubMed's Language field says what the *article* is in, but it isn't always
# reliable for what PMC actually serves, so the extracted body gets checked
# directly. Non-English text embeds poorly against English queries and would
# be unusable in an English answer even if retrieved.
_NON_LATIN_RANGES = (
    (0x0400, 0x04FF),  # Cyrillic
    (0x0600, 0x06FF),  # Arabic
    (0x0900, 0x097F),  # Devanagari
    (0x3040, 0x30FF),  # Hiragana + Katakana
    (0x3400, 0x4DBF),  # CJK extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xAC00, 0xD7AF),  # Hangul
)
MAX_NON_LATIN_RATIO = 0.10


def _non_latin_ratio(text: str) -> float:
    """Fraction of non-whitespace characters outside Latin scripts."""
    considered = [char for char in text if not char.isspace()]
    if not considered:
        return 0.0

    non_latin = sum(
        1
        for char in considered
        if any(low <= ord(char) <= high for low, high in _NON_LATIN_RANGES)
    )
    return non_latin / len(considered)


def _rate_limit_delay(api_key: str | None) -> float:
    """Returns the sleep interval to use between E-utilities calls."""
    return _WITH_KEY_DELAY_SECONDS if api_key else _NO_KEY_DELAY_SECONDS


def _element_text(element: ET.Element) -> str:
    """Flattens an element to text, dropping citation markers and figures.

    Keeps the `tail` of skipped children so removing an inline <xref> in the
    middle of a sentence doesn't also swallow the rest of that sentence.
    """
    parts: list[str] = []
    if element.text:
        parts.append(element.text)

    for child in element:
        if child.tag not in _SKIP_SUBTREE_TAGS:
            parts.append(_element_text(child))
        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


def clean_text(text: str) -> str:
    """Collapses whitespace and tidies spacing left behind by dropped markers.

    Removing an <xref> leaves the brackets that wrapped it - "Gotink et al.
    [] found" - which is both noise and a collision risk with the [1]-style
    citation markers the generation step emits, so empty brackets go too.
    """
    # Paragraph breaks survive: a single <p> never contains one, so extraction
    # is unaffected - but when this is re-applied to already-joined section
    # text, the splitter still gets "\n\n" boundaries to prefer.
    paragraphs = []
    for paragraph in text.split("\n\n"):
        paragraph = re.sub(r"\s+", " ", paragraph)
        paragraph = re.sub(r"[\[\(]\s*[,;\-–]*\s*[\]\)]", "", paragraph)
        paragraph = re.sub(r"\s+([,.;:)\]])", r"\1", paragraph)
        paragraph = re.sub(r"\s{2,}", " ", paragraph).strip()
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def normalize_section_title(title: str) -> str:
    """Normalizes a section heading so equivalent sections read alike.

    Publishers style the same section a dozen ways - "Discussion",
    "DISCUSSION", "4. Discussion", "2.2.1. Depressive Symptoms". Left alone
    those become distinct prefixes on the embedded text and therefore
    distinct signals for the same concept, so they're folded together here.
    """
    title = re.sub(r"\{[^}]*\}", "", title)
    title = re.sub(r"^\d+(\.\d+)*[\.\)]?\s*", "", title).strip()
    title = title.rstrip(":.").strip()
    if title.isupper() and len(title) > 3:
        title = title.title()
    return title


def _section_title(sec: ET.Element) -> str | None:
    """Returns a <sec>'s own title text, if it has one."""
    title = sec.find("title")
    if title is None:
        return None
    text = normalize_section_title(clean_text(_element_text(title)))
    return text or None


def is_dropped_section(title_path: list[str]) -> bool:
    """True if any title in the path matches the drop list.

    Checks the whole path, not just the deepest title, so a subsection like
    "Methods > Ethical considerations" is dropped on the child's title while
    "Introduction > Study rationale" is dropped on the parent's.
    """
    for title in title_path:
        lowered = title.lower()
        if any(pattern in lowered for pattern in _DROP_SECTION_PATTERNS):
            return True
    return False


def _direct_paragraphs(sec: ET.Element) -> str:
    """Joins the <p> children belonging to this section, not its subsections."""
    paragraphs = [clean_text(_element_text(p)) for p in sec.findall("p")]
    return "\n\n".join(p for p in paragraphs if p)


def _walk_sections(
    element: ET.Element, title_path: list[str], out: list[dict]
) -> None:
    """Recursively collects {section, text} entries from a <sec> tree."""
    for sec in element.findall("sec"):
        title = _section_title(sec)
        path = [*title_path, title] if title else list(title_path)

        if not is_dropped_section(path):
            text = _direct_paragraphs(sec)
            if text:
                out.append({"section": path[-1] if path else "Body", "text": text})

        _walk_sections(sec, path, out)


def parse_jats_sections(xml_bytes: bytes) -> list[dict]:
    """Extracts the keepable body sections from one PMC article's JATS XML.

    Returns a list of {"section": str, "text": str}. <back> is never walked,
    so references/funding/acknowledgements are excluded by construction.
    Articles whose body has no <sec> structure fall back to a single
    "Full text" section rather than being discarded.
    """
    root = ET.fromstring(xml_bytes)
    body = root.find(".//body")
    if body is None:
        return []

    sections: list[dict] = []
    _walk_sections(body, [], sections)

    if not sections:
        loose = _direct_paragraphs(body)
        if loose:
            sections.append({"section": "Full text", "text": loose})

    return sections


def fetch_full_text(pmcid: str, api_key: str | None = None) -> list[dict]:
    """Fetches and parses one article's full text from PMC.

    Args:
        pmcid: The PMC identifier, with or without the "PMC" prefix.
        api_key: Optional NCBI API key; raises the rate limit 3 -> 10 req/sec.

    Returns:
        A list of {"section", "text"} dicts, or an empty list when the article
        has no servable body (most non-open-access deposits), is too short to
        be a real article, or isn't in English.
    """
    params = {
        "db": "pmc",
        "id": pmcid.replace("PMC", ""),
        "retmode": "xml",
    }
    if api_key:
        params["api_key"] = api_key

    response = requests.get(EFETCH_URL, params=params, timeout=60)
    response.raise_for_status()
    time.sleep(_rate_limit_delay(api_key))

    sections = parse_jats_sections(response.content)

    body = "".join(section["text"] for section in sections)
    if len(body) < MIN_BODY_CHARS:
        return []
    if _non_latin_ratio(body) > MAX_NON_LATIN_RATIO:
        return []

    return sections
