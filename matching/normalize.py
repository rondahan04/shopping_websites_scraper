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

# Phrases only — avoid matching "case" inside "in case you…" etc.
ACCESSORY_SUBSTRINGS: tuple[str, ...] = (
    "laptop bag",
    "laptop briefcase",
    "briefcase",
    "notebook bag",
    "shoulder bag",
    "carrying case",
    "case for",
    "cover for",
    "folio for",
    "phone case",
    "tablet case",
    "keyboard case",
    "charging case",
    "protective case",
    "screen protector",
    "tempered glass",
    "charger only",
    "cable only",
    "replacement part",
    "replacement earpad",
    "replacement earpads",
    "earpads replacement",
    "earpad for",
    "earpads for",
    "ear cushions",
    "ear pads cushions",
    "replacement cups",
    "sheepskin replacement",
    "leather ear pads",
    "leather earpads",
    "velour earpads",
    "velour ear pads",
    "velour pads",
    "memory foam earpads",
    "memory foam ear pads",
    "earmuff replacement",
    "replacement earmuffs",
    "tv mount",
    "dash mount",
    "monitor mount",
    "tripod mount",
    "desk mount",
    "stand only",
    "case compatible",
    "cover compatible",
    "sleeve for",
    "holder for",
    "shell for",
)

BUNDLE_KEYWORDS = frozenset({"bundle", "2-pack", "3-pack", "combo", "+ keyboard", "with keyboard"})

# TV + soundbar bundles when the user asked for the standalone device.
_BUNDLE_LISTING_MARKERS: tuple[str, ...] = (
    "bundle",
    "soundbar",
    "sound bar",
    "wireless-speaker",
    "wireless-speakers",
    "wireless-soundbar",
    "matching sound",
    "with soundbar",
    "channel matching",
    "protection bundle",
)

_INCH_SIZE_RE = re.compile(r"\b(\d{2})\s*-?\s*inch\b", re.I)
_OLED_SIZE_IN_MODEL_RE = re.compile(r"oled(\d{2})", re.I)

DEVICE_QUERY_MARKERS: tuple[str, ...] = (
    "macbook",
    "laptop",
    "notebook",
    "tablet",
    "ipad",
    "chromebook",
    "surface pro",
    "surface laptop",
    # Audio devices — so case/cover/sleeve guard also fires for earbuds/headphones
    "airpods",
    "earbuds",
    "headphone",
    "headphones",
    "earphones",
    "speaker",
    "soundbar",
    "monitor",
    "keyboard",
    "mouse",
    "webcam",
    "microphone",
)

PERIPHERAL_ACCESSORY_MARKERS: tuple[str, ...] = (
    "charger",
    "power adapter",
    "usb-c adapter",
    "usb c adapter",
    "charging cable",
    "charging adapter",
    "replacement battery",
    "docking station",
    "usb c hub",
    "hub adapter",
)

ALIAS_REPLACEMENTS = [
    (r"\bgb\b", "gigabyte"),
    (r"\btb\b", "terabyte"),
    (r"\bgen\s*(\d+)\b", r"generation \1"),
    (r"\b(\d{1,2})\s*inch\b", r"\1 inch"),
    (r"\b(\d{1,2})\"\b", r"\1 inch"),
]

MODEL_TOKEN_RE = re.compile(
    r"\b(?:[a-z]{1,3}\d{2,5}|\d{4}|[a-z]+\d+[a-z]*\d*|m[1-9])\b",
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


def has_peripheral_accessory_conflict(query_norm: NormalizedText, title_norm: NormalizedText) -> bool:
    """Chargers/adapters for device queries (e.g. 'MacBook Air Charger' when searching for a MacBook)."""
    q = query_norm.normalized
    t = title_norm.normalized
    if not any(m in q for m in DEVICE_QUERY_MARKERS):
        return False
    if not any(m in t for m in PERIPHERAL_ACCESSORY_MARKERS):
        return False
    if re.search(r"^(refurbished\s+)?apple\s+macbook\s+(pro|air)\b", t):
        return False
    product_part = t.split("compatible with", 1)[0][:140]
    if not any(m in product_part for m in PERIPHERAL_ACCESSORY_MARKERS):
        return False
    if re.search(r"\bmacbook\s+(air|pro)\s+charger\b", product_part):
        return True
    if re.search(r"\b(charger|power adapter|charging adapter)\b", product_part):
        if re.search(r"\b\d{1,2}\s*inch\b", product_part) and re.search(
            r"\b(\d+\s*gb|\d+\s*tb|ssd|m[1-9]\s+chip)\b",
            product_part,
        ):
            return False
        return True
    if re.search(r"\b(usb c hub|docking station|hub adapter)\b", product_part):
        if not re.search(r"^(refurbished\s+)?apple\s+macbook", product_part):
            return True
    return False


_EARBUD_MARKERS = ("earbud", "earbuds", "in-ear", "in ear", "true wireless")
# Amazon ASINs that are QC Ultra earbuds but SERP titles often omit "earbuds".
_AMAZON_EARBUD_ASINS = frozenset({"B0D6WCQWJS", "B0D6WBKCPD"})
_OVEREAR_MARKERS = ("over-ear", "over ear", "over the ear", "around-ear", "around ear")


def has_earbuds_vs_headphones_conflict(query_norm: NormalizedText, title_norm: NormalizedText) -> bool:
    """Query targets over-ear headphones but listing title is clearly earbuds (or vice versa)."""
    q = query_norm.normalized
    t = title_norm.normalized
    q_wants_headphones = "headphone" in q and "earbud" not in q
    q_wants_earbuds = "earbud" in q and "headphone" not in q
    t_is_earbuds = any(m in t for m in _EARBUD_MARKERS)
    t_is_overear = any(m in t for m in _OVEREAR_MARKERS)
    if q_wants_headphones and t_is_earbuds and not t_is_overear:
        return True
    if q_wants_earbuds and t_is_overear and not t_is_earbuds:
        return True
    return False


def amazon_asin_from_url(url: str) -> str | None:
    m = re.search(r"/dp/([A-Z0-9]{10})", url, re.I)
    return m.group(1).upper() if m else None


def is_amazon_earbuds_asin_for_headphone_query(query_norm: NormalizedText, url: str) -> bool:
    """Block known earbud ASINs when the user query targets over-ear headphones."""
    q = query_norm.normalized
    if "headphone" not in q or "earbud" in q:
        return False
    asin = amazon_asin_from_url(url)
    return bool(asin and asin in _AMAZON_EARBUD_ASINS)


def has_accessory_conflict(query_norm: NormalizedText, title_norm: NormalizedText) -> bool:
    if has_peripheral_accessory_conflict(query_norm, title_norm):
        return True
    title_lower = title_norm.normalized
    query_lower = query_norm.normalized
    if any(m in query_lower for m in DEVICE_QUERY_MARKERS) and "case" not in query_lower:
        head = title_lower.split("compatible with", 1)[0][:140]
        if re.search(r"\b(case|cover|folio|shell|sleeve)\b", head):
            if not re.search(r"^(refurbished\s+)?apple\s+macbook\s+(pro|air)\b", head):
                return True
        if re.search(r"\b(usb c hub|docking station|hub adapter)\b", head):
            if not re.search(r"^(refurbished\s+)?apple\s+macbook", head):
                return True
    if re.search(r"\bapple\s+macbook\b", query_lower) or (
        "macbook" in query_lower and "apple" in query_lower
    ):
        head = title_lower.split("compatible with", 1)[0][:100]
        if not re.search(r"\b(apple|macbook)\b", head):
            return True
    for phrase in ACCESSORY_SUBSTRINGS:
        if phrase in title_lower and phrase not in query_lower:
            return True
    if (
        "keyboard" in title_lower
        and "case" in title_lower
        and "keyboard" not in query_lower
        and "case" not in query_lower
    ):
        return True
    return False


def has_chip_generation_mismatch(query_norm: NormalizedText, title_norm: NormalizedText) -> bool:
    """Reject listings with an older Apple Silicon generation than the query (e.g. M1 vs M5)."""
    q_chips = [int(m.group(1)) for m in re.finditer(r"\bm([1-9])\b", query_norm.normalized, re.I)]
    if not q_chips:
        return False
    q_target = max(q_chips)
    t_chips = [int(m.group(1)) for m in re.finditer(r"\bm([1-9])\b", title_norm.normalized, re.I)]
    if not t_chips:
        return False
    if max(t_chips) < q_target:
        return True
    # "M1-M5 (2021-2022)" case/cover listings span below the requested chip.
    if len(t_chips) >= 2 and min(t_chips) < q_target:
        return True
    return False


def has_model_code_mismatch(query_norm: NormalizedText, title_norm: NormalizedText) -> bool:
    """Require alphanumeric model codes from the query (e.g. p12) in the listing text.

    Apple Silicon chips (m1–m9) are excluded: SERPs often only list older gens (M1 refurb)
    while the user asked for M5 — those are still laptops, not accessories.
    """
    codes = [
        t
        for t in query_norm.model_tokens
        if len(t) >= 2
        and any(ch.isdigit() for ch in t)
        and any(ch.isalpha() for ch in t)
        and not re.fullmatch(r"m[1-9]", t.lower())
    ]
    if not codes:
        return False
    hay = title_norm.normalized
    return any(code.lower() not in hay for code in codes)


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
    for marker in _BUNDLE_LISTING_MARKERS:
        if marker in title_lower and marker not in query_norm.normalized:
            penalty += 12.0
    return penalty


def _inch_sizes_from_text(*blobs: str) -> set[int]:
    sizes: set[int] = set()
    for blob in blobs:
        if not blob:
            continue
        for m in _INCH_SIZE_RE.finditer(blob):
            sizes.add(int(m.group(1)))
        for m in re.finditer(r"\b(\d{2})\s*class\b", blob, re.I):
            sizes.add(int(m.group(1)))
        for m in _OLED_SIZE_IN_MODEL_RE.finditer(blob):
            sizes.add(int(m.group(1)))
    return sizes


def has_bundle_conflict(
    query_norm: NormalizedText,
    title_norm: NormalizedText,
    url: str = "",
) -> bool:
    """Reject TV+soundbar (etc.) bundles when the query does not ask for a bundle."""
    q = query_norm.normalized
    if any(kw in q for kw in ("bundle", "soundbar", "sound bar", "combo", "with soundbar")):
        return False
    blob = f"{title_norm.normalized} {url.lower()}"
    return any(marker in blob for marker in _BUNDLE_LISTING_MARKERS)


def has_screen_size_mismatch(
    query_norm: NormalizedText,
    title_norm: NormalizedText,
    url: str = "",
) -> bool:
    """Reject listings with a different screen size than the query (e.g. 48\" vs 65\")."""
    q_sizes = _inch_sizes_from_text(query_norm.normalized, " ".join(query_norm.model_tokens))
    if not q_sizes:
        return False
    t_sizes = _inch_sizes_from_text(title_norm.normalized, url)
    if not t_sizes:
        return False
    if q_sizes & t_sizes:
        return False
    return True
