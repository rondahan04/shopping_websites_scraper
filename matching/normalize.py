"""Text normalization for product title matching."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "with",
        "in",
        "on",
        "at",
        "to",
        "of",
        "by",
        "from",
        "new",
        "free",
        "shipping",
    }
)

ACCESSORY_KEYWORDS = frozenset(
    {
        "case",
        "cover",
        "screen protector",
        "charger only",
        "cable only",
        "mount",
        "stand only",
        "replacement part",
        "tempered glass",
    }
)

BUNDLE_KEYWORDS = frozenset({"bundle", "2-pack", "3-pack", "combo", "+ keyboard", "with keyboard"})

ALIAS_REPLACEMENTS = [
    (r"\bgb\b", "gigabyte"),
    (r"\btb\b", "terabyte"),
    (r"\bgen\s*(\d+)\b", r"generation \1"),
    (r"\b(\d{1,2})\s*inch\b", r"\1 inch"),
    (r"\b(\d{1,2})\"\b", r"\1 inch"),
]

MODEL_TOKEN_RE = re.compile(
    r"\b(?:[a-z]{1,3}\d{2,5}|\d{4}|[a-z]+\d+[a-z]*\d*)\b",
    re.I,
)

@dataclass
class NormalizedText:
    raw: str
    normalized: str
    tokens: list[str]
    model_tokens: list[str]
    years: list[str]


def normalize_text(text: str) -> NormalizedText:
    raw = text
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s\-\.]", " ", s)
    for pattern, repl in ALIAS_REPLACEMENTS:
        s = re.sub(pattern, repl, s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()

    tokens = [t for t in s.split() if t and t not in STOPWORDS]
    model_tokens = list(dict.fromkeys(MODEL_TOKEN_RE.findall(s)))
    years_found = re.findall(r"\b((?:19|20)\d{2})\b", s)

    return NormalizedText(
        raw=raw,
        normalized=s,
        tokens=tokens,
        model_tokens=model_tokens,
        years=years_found,
    )


def has_accessory_conflict(query_norm: NormalizedText, title_norm: NormalizedText) -> bool:
    title_lower = title_norm.normalized
    query_lower = query_norm.normalized
    for kw in ACCESSORY_KEYWORDS:
        if kw in title_lower and kw not in query_lower:
            return True
    return False


def has_year_conflict(query_norm: NormalizedText, title_norm: NormalizedText) -> bool:
    if not query_norm.years:
        return False
    q_year = query_norm.years[0]
    if title_norm.years and q_year not in title_norm.years:
        return True
    return False


def model_token_recall(query_norm: NormalizedText, title_norm: NormalizedText) -> float:
    if not query_norm.model_tokens:
        return 1.0
    title_set = set(title_norm.model_tokens)
    hits = sum(1 for t in query_norm.model_tokens if t.lower() in {x.lower() for x in title_set})
    return hits / len(query_norm.model_tokens)


def bundle_penalty(query_norm: NormalizedText, title_norm: NormalizedText) -> float:
    title_lower = title_norm.normalized
    penalty = 0.0
    for kw in BUNDLE_KEYWORDS:
        if kw in title_lower and kw not in query_norm.normalized:
            penalty += 8.0
    return penalty
