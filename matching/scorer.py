"""Similarity scoring and best-match selection."""

from __future__ import annotations

from urllib.parse import urlparse

from config import SETTINGS
from matching.condition import condition_score_penalty
from matching.normalize import (
    bundle_penalty,
    has_accessory_conflict,
    has_chip_generation_mismatch,
    has_earbuds_vs_headphones_conflict,
    has_model_code_mismatch,
    has_year_conflict,
    model_token_recall,
    normalize_text,
)
from models import MatchCandidate, SearchResult
from rapidfuzz import fuzz


def score_title(query: str, title: str) -> tuple[float, dict]:
    qn = normalize_text(query)
    tn = normalize_text(title)

    if has_accessory_conflict(qn, tn):
        return 0.0, {"filtered": "accessory"}
    if has_earbuds_vs_headphones_conflict(qn, tn):
        return 0.0, {"filtered": "earbuds_vs_headphones"}
    if has_model_code_mismatch(qn, tn):
        return 0.0, {"filtered": "model_code"}
    if has_chip_generation_mismatch(qn, tn):
        return 0.0, {"filtered": "chip_generation"}
    if has_year_conflict(qn, tn):
        return 0.0, {"filtered": "year"}

    wratio = fuzz.WRatio(qn.normalized, tn.normalized)
    token_set = fuzz.token_set_ratio(qn.normalized, tn.normalized)
    recall = model_token_recall(qn, tn) * 100.0

    year_bonus = 0.0
    if qn.years and tn.years and qn.years[0] in tn.years:
        year_bonus = 5.0
    elif qn.years and tn.years and qn.years[0] not in tn.years:
        year_bonus = -10.0

    condition_penalty = condition_score_penalty(query, title)
    score = (
        0.55 * wratio
        + 0.25 * token_set
        + 0.15 * recall
        + 0.05 * year_bonus
        - bundle_penalty(qn, tn)
        - condition_penalty
    )
    score = max(0.0, min(100.0, score))
    return score, {
        "wratio": wratio,
        "token_set": token_set,
        "model_recall": recall,
        "year_bonus": year_bonus,
        "condition_penalty": condition_penalty,
    }


def pick_best_match(
    query: str,
    results: list[SearchResult],
) -> tuple[SearchResult | None, list[MatchCandidate]]:
    if not results:
        return None, []

    candidates: list[MatchCandidate] = []
    for r in results:
        # Use URL path only—tracking query params often contain the search string (false p12 match).
        path = urlparse(r.url).path if r.url else ""
        score, details = score_title(query, f"{r.title} {path}")
        if details.get("filtered"):
            continue
        candidates.append(MatchCandidate(result=r, score=score, details=details))

    if not candidates:
        qn_static = normalize_text(query)
        for r in results:
            path = urlparse(r.url).path if r.url else ""
            tn = normalize_text(f"{r.title} {path}")
            if (
                has_accessory_conflict(qn_static, tn)
                or has_model_code_mismatch(qn_static, tn)
                or has_year_conflict(qn_static, tn)
            ):
                continue
            wratio = fuzz.WRatio(qn_static.normalized, tn.normalized)
            candidates.append(
                MatchCandidate(result=r, score=wratio, details={"fallback": True})
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    if not candidates:
        return None, []

    best = candidates[0]
    if best.score >= SETTINGS.min_match_score:
        return best.result, candidates

    # Firecrawl / noisy SERPs often land just under the hard cutoff while still being the right SKU row.
    if (
        best.score >= SETTINGS.min_match_score_soft_floor
        and not best.details.get("fallback")
        and float(best.details.get("model_recall", 0.0)) >= 55.0
    ):
        return best.result, candidates

    # Salvage titles from URL slugs (Best Buy) may score low on wratio but match model tokens.
    if (
        not best.details.get("fallback")
        and float(best.details.get("model_recall", 0.0)) >= 50.0
        and float(best.details.get("token_set", 0.0)) >= 45.0
    ):
        return best.result, candidates

    return None, candidates
