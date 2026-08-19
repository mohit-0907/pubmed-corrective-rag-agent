"""Crisis-language screening for incoming questions.

Deliberately a simple keyword/pattern check, not an LLM call or clinical
classifier - this is a portfolio project, and the whole point of this
guardrail is to reliably bypass the RAG pipeline (retrieval + generation
from research abstracts is never an appropriate response to acute
distress) rather than trust an LLM to catch every case. See README for the
explicit limitations of this approach.
"""

from __future__ import annotations

import re

_CRISIS_PATTERNS = [
    r"suicid\w*",
    r"kill(ing)?\s+(myself|my\s*self)",
    r"end(ing)?\s+(my\s+life|it\s+all)",
    r"take\s+my\s+(own\s+)?life",
    r"want(ed)?\s+to\s+die",
    r"wish(ed)?\s+(i\s+was|i\s+were)\s+dead",
    r"better\s+off\s+dead",
    r"no\s+reason\s+to\s+live",
    r"not\s+worth\s+living",
    r"can'?t\s+go\s+on(\s+living)?",
    r"self[\s-]?harm",
    r"hurt(ing)?\s+myself",
    r"cutt?ing\s+myself",
    r"overdose",
]

_CRISIS_REGEX = re.compile("|".join(_CRISIS_PATTERNS), re.IGNORECASE)

CRISIS_RESPONSE = """\
I'm not able to help with this through research-literature summaries, but please reach out for support right now:

- US: Call or text 988 (Suicide & Crisis Lifeline) - available 24/7
- US: Text HOME to 741741 (Crisis Text Line)
- Outside the US: https://findahelpline.com lists crisis lines by country
- If you're in immediate danger, call your local emergency number (911 in the US) or go to the nearest emergency room

You deserve support from a real person. This is an automated research tool and isn't equipped to help in a crisis."""


def is_crisis_message(question: str) -> bool:
    """True if the question matches known crisis/self-harm language patterns."""
    return bool(_CRISIS_REGEX.search(question))
