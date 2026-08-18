import pytest

from plastered.release_search.title_matching import (
    CANDIDATE_TOKEN_SUBSET_SCORE,
    EXACT_MATCH_SCORE,
    MIN_MATCH_SCORE,
    QUERY_TOKEN_SUBSET_SCORE,
    normalize_title,
    title_match_score,
)


@pytest.mark.parametrize(
    "raw_title, expected",
    [
        ("Some Album", "some album"),
        ("  Some   Album  ", "some album"),
        ("SOME ALBUM", "some album"),
        # Diacritics are stripped, '&' unifies with 'and', punctuation becomes spaces.
        ("Café & Co. — Remastered", "cafe and co remastered"),
        ("Much Against Everyone's Advice", "much against everyone s advice"),
        ("Much Against Everyone’s Advice", "much against everyone s advice"),
        ("OK Computer OKNOTOK 1997 2017", "ok computer oknotok 1997 2017"),
        # Non-latin alphanumeric characters are preserved.
        ("宇宙 Nihongo", "宇宙 nihongo"),
        # A pure-symbol title normalizes to the empty string.
        ("†", ""),
    ],
)
def test_normalize_title(raw_title: str, expected: str) -> None:
    assert normalize_title(raw_title) == expected


@pytest.mark.parametrize(
    "wanted, candidate, fuzzy_enabled, expected",
    [
        # Exact and normalization-insensitive exact matches, both modes.
        ("Some Album", "Some Album", False, EXACT_MATCH_SCORE),
        ("Some Album", "some album!", False, EXACT_MATCH_SCORE),
        ("Much Against Everyone's Advice", "Much Against Everyone’s Advice", False, EXACT_MATCH_SCORE),
        ("Sgt. Pepper & Friends", "Sgt Pepper and Friends", False, EXACT_MATCH_SCORE),
        # Wanted-words-subset (mirrors RED's own word-level groupname matching), both modes.
        ("OK Computer", "OK Computer OKNOTOK 1997 2017", False, QUERY_TOKEN_SUBSET_SCORE),
        ("OK Computer", "OK Computer OKNOTOK 1997 2017", True, QUERY_TOKEN_SUBSET_SCORE),
        # Candidate-words-subset only matches in fuzzy mode.
        ("Some Album (Deluxe Edition)", "Some Album", True, CANDIDATE_TOKEN_SUBSET_SCORE),
        ("Some Album (Deluxe Edition)", "Some Album", False, 0.0),
        # Unrelated titles never match.
        ("Untrue", "Burial", False, 0.0),
        # Pure-symbol titles fall back to direct comparison instead of matching any other symbol title.
        ("†", "†", False, EXACT_MATCH_SCORE),
        ("†", "‡", True, 0.0),
    ],
)
def test_title_match_score(wanted: str, candidate: str, fuzzy_enabled: bool, expected: float) -> None:
    assert title_match_score(wanted, candidate, fuzzy_enabled) == expected


def test_title_match_score_fuzzy_ratio_tier() -> None:
    """Near-identical titles score via the difflib ratio tier only when fuzzy matching is enabled."""
    wanted, candidate = "Some Bad Album (Deluxe Edition)", "Some Bad Album (Deluxe Editions)"
    fuzzy_score = title_match_score(wanted, candidate, fuzzy_enabled=True)
    assert MIN_MATCH_SCORE <= fuzzy_score < EXACT_MATCH_SCORE
    assert title_match_score(wanted, candidate, fuzzy_enabled=False) == 0.0


def test_title_match_score_reordered_tokens_match_in_both_modes() -> None:
    """Identical word sets in a different order hit the word-subset tier, so they match even without fuzzy."""
    assert (
        title_match_score("Deluxe Edition Some Album", "Some Album Deluxe Edition", fuzzy_enabled=False)
        == QUERY_TOKEN_SUBSET_SCORE
    )


def test_title_match_score_fuzzy_sorted_token_ratio() -> None:
    """The sorted-token ratio catches reordered near-identical word sets the plain character ratio misses."""
    wanted, candidate = "Album Deluxe Edition Bonus", "Deluxe Album Editions Bonus"
    from difflib import SequenceMatcher

    char_ratio = SequenceMatcher(None, normalize_title(wanted), normalize_title(candidate)).ratio()
    fuzzy_score = title_match_score(wanted, candidate, fuzzy_enabled=True)
    assert fuzzy_score >= MIN_MATCH_SCORE
    assert fuzzy_score > char_ratio
