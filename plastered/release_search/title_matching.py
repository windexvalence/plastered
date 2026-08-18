"""
Client-side release-title matching for RED release groups.

RED's search offers no fuzzy matching or similar-word options, so instead of relying on the browse endpoint's exact
`groupname` param, the searcher fetches an artist's full release-group listing (`RedAPIClient.get_artist_release_groups`)
and matches the wanted release title against the group names here (see `SearchState.get_candidate_release_groups`).
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher
from typing import Final

# Score for a normalized-exact title match; the ranking ceiling.
EXACT_MATCH_SCORE: Final[float] = 1.0
# Score when every word of the wanted title appears in the candidate group name (e.g. group "X (Deluxe Edition)" for
# wanted "X") — this mirrors the word-level matching RED's own Sphinx-backed `groupname` browse param provided.
QUERY_TOKEN_SUBSET_SCORE: Final[float] = 0.9
# Fuzzy-only: score when every word of the candidate group name appears in the wanted title (e.g. group "X" for
# wanted "X (Deluxe Edition)").
CANDIDATE_TOKEN_SUBSET_SCORE: Final[float] = 0.85
# Minimum score for a candidate group to be considered a title match at all.
MIN_MATCH_SCORE: Final[float] = 0.8


def normalize_title(title: str) -> str:
    """
    Canonicalizes a release title for comparison: casefolds, strips diacritics, unifies '&' with 'and', replaces
    punctuation (curly quotes, dashes, brackets, ...) with spaces, and collapses runs of whitespace.
    """
    decomposed = unicodedata.normalize("NFKD", title.casefold())
    stripped_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    unified = stripped_accents.replace("&", " and ")
    alphanumeric_only = "".join(char if (char.isalnum() or char.isspace()) else " " for char in unified)
    return " ".join(alphanumeric_only.split())


def title_match_score(wanted_title: str, candidate_title: str, fuzzy_enabled: bool) -> float:
    """
    Scores how well a RED group name matches the wanted release title, in [0.0, 1.0]; callers treat scores >=
    `MIN_MATCH_SCORE` as a match.

    Without `fuzzy_enabled` only the exact and wanted-words-subset tiers apply (see the score constants above), which
    mirrors what RED's own `groupname` browse matching accepted; anything else scores 0.0. With `fuzzy_enabled`, two
    lenient tiers are added: the candidate-words-subset tier (a plain "X" group for a wanted "X (Deluxe Edition)"),
    and otherwise the best `difflib` ratio between the normalized titles / their sorted-token forms.
    """
    norm_wanted, norm_candidate = normalize_title(wanted_title), normalize_title(candidate_title)
    if not norm_wanted or not norm_candidate:
        # A title made up entirely of punctuation/symbols (e.g. "†") normalizes to the empty string; fall back to a
        # direct case-insensitive comparison rather than treating two empty normalizations as equal.
        return EXACT_MATCH_SCORE if wanted_title.casefold() == candidate_title.casefold() else 0.0
    if norm_wanted == norm_candidate:
        return EXACT_MATCH_SCORE
    wanted_tokens, candidate_tokens = set(norm_wanted.split()), set(norm_candidate.split())
    if wanted_tokens <= candidate_tokens:
        return QUERY_TOKEN_SUBSET_SCORE
    if not fuzzy_enabled:
        return 0.0
    if candidate_tokens <= wanted_tokens:
        return CANDIDATE_TOKEN_SUBSET_SCORE
    return max(
        SequenceMatcher(None, norm_wanted, norm_candidate).ratio(),
        SequenceMatcher(None, " ".join(sorted(wanted_tokens)), " ".join(sorted(candidate_tokens))).ratio(),
    )
