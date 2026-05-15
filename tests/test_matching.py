"""Unit tests for similarity matching."""

from matching.scorer import pick_best_match, score_title
from models import SearchResult


def test_scores_exact_model_higher():
    query = "Lenovo Tab P12-2024"
    good = "Lenovo Tab P12 12.7 inch Tablet 2024"
    bad = "Lenovo Tab M10 Case with Screen Protector"
    assert score_title(query, good)[0] > score_title(query, bad)[0]


def test_pick_best_match_selects_correct_product():
    query = "Lenovo Tab P12-2024"
    results = [
        SearchResult(title="USB-C Charger for Lenovo Tablets", url="https://a.com/1", rank=1),
        SearchResult(
            title="Lenovo Tab P12 12.7\" Tablet 256GB 2024 Model",
            url="https://a.com/2",
            rank=2,
        ),
        SearchResult(title="Lenovo Tab M10 Plus", url="https://a.com/3", rank=3),
    ]
    match, _ = pick_best_match(query, results)
    assert match is not None
    assert "P12" in match.title


def test_keyboard_case_combo_filtered_when_query_is_device_only():
    query = "Lenovo Tab P12-2024"
    bad_title = (
        "BONAEVER Case with Trackpad Keyboard for Lenovo Tab P12 "
        "12.7 inch 2023 2024 / Lenovo Tab Extreme"
    )
    score, details = score_title(query, bad_title)
    assert score == 0.0
    assert details.get("filtered") == "accessory"


def test_pick_best_match_returns_none_below_threshold():
    query = "Lenovo Tab P12-2024"
    results = [
        SearchResult(title="Completely Unrelated Product XYZ", url="https://a.com/1", rank=1),
    ]
    match, candidates = pick_best_match(query, results)
    assert match is None
    assert candidates


def test_pick_best_fallback_does_not_pick_case_only_listing():
    query = "Lenovo Tab P12-2024"
    results = [
        SearchResult(
            title="WERLEO Case for Lenovo Tab P12 12.7 inch 2024 2023 TB370FU TB371FC",
            url="https://newegg.com/case/1",
            rank=1,
        ),
    ]
    match, candidates = pick_best_match(query, results)
    assert match is None
    assert candidates == []
