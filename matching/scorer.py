"""Similarity scoring and best-match selection."""

from __future__ import annotations

from config import SETTINGS
from matching.normalize import (
    bundle_penalty,
    has_accessory_conflict,
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

    score = (
        0.55 * wratio
        + 0.25 * token_set
        + 0.15 * recall
        + 0.05 * year_bonus
        - bundle_penalty(qn, tn)
    )
    score = max(0.0, min(100.0, score))
    return score, {
        "wratio": wratio,
        "token_set": token_set,
        "model_recall": recall,
        "year_bonus": year_bonus,
    }


def pick_best_match(
    query: str,
    results: list[SearchResult],
) -> tuple[SearchResult | None, list[MatchCandidate]]:
    if not results:
        return None, []

    candidates: list[MatchCandidate] = []
    for r in results:
        score, details = score_title(query, r.title)
        if details.get("filtered"):
            continue
        candidates.append(MatchCandidate(result=r, score=score, details=details))

    if not candidates:
        # Fallback: score all without hard filters
        for r in results:
            qn = normalize_text(query)
            tn = normalize_text(r.title)
            wratio = fuzz.WRatio(qn.normalized, tn.normalized)
            candidates.append(
                MatchCandidate(result=r, score=wratio, details={"fallback": True})
            )

    candidates.sort(key=lambda c: c.score, reverse=True)
    if not candidates:
        return None, []

    best = candidates[0]
    if best.score < SETTINGS.min_match_score:
        return None, candidates

    return best.result, candidates
