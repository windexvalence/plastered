"""Implementations of the `SearchItemModifier` abstract base class should live in this file."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plastered.db.db_models import SearchRecord
from plastered.db.db_utils import add_record, upsert_resolved_origin
from plastered.models import LFMAlbumInfo, MBRelease, OriginRelease, rank_origin_candidates
from plastered.release_search.processors.bases import SearchItemModifier
from plastered.utils.constants import MUSICBRAINZ_LOOKUP_LINKED_ENTITY_CAP
from plastered.utils.exceptions import (
    LFMClientException,
    LFMRequestFailureException,
    MusicBrainzClientException,
    MusicBrainzRequestFailureException,
)

if TYPE_CHECKING:
    from plastered.models import SearchItem
    from plastered.release_search.search_helpers import SearchState
    from plastered.utils.http_clients import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient

_LOGGER = logging.getLogger(__name__)


class ResolveAlbumInfoModifier(SearchItemModifier):
    """Intended as replacement for `ReleaseSearcher._resolve_lfm_album_info`."""

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        if si.is_manual:
            return si
        try:
            lfmai = LFMAlbumInfo.construct_from_api_response(json_blob=lfm.get_album_info(si=si))
        except LFMClientException as ex:
            _LOGGER.debug(f"{ex.__class__.__name__} during LFM album info resolution for search item: {si}")
            if isinstance(ex, LFMRequestFailureException):
                si.lfm_request_failed = True
            lfmai = None
        si.set_lfm_album_info(lfmai=lfmai)
        return si


class ResolveTrackOriginModifier(SearchItemModifier):
    """
    Resolves a track item's candidate origin releases, ranked best-first (see `rank_origin_candidates`): the release
    LFM associates with the track plus every release MusicBrainz lists for the recording — via the recording lookup
    when LFM supplies the recording MBID, and via the recording search when it doesn't or when the lookup comes back
    empty (stale MBID, artist mismatch) or capped. The top candidate becomes `si.release_name` and is persisted as the
    item's resolved origin (see `upsert_resolved_origin`).
    """

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        lfm_candidate: OriginRelease | None = None
        recording_mbid: str | None = None
        artist_mbid: str | None = None
        try:
            lfm_resp: dict[str, Any] = lfm.get_track_info(si=si)
            lfm_candidate = OriginRelease.from_lfm_track_info(json_blob=lfm_resp)
            recording_mbid = lfm_resp.get("mbid") or None
            artist_json = lfm_resp.get("artist")
            artist_mbid = (artist_json.get("mbid") or None) if isinstance(artist_json, dict) else None
        except (LFMClientException, AttributeError, KeyError, TypeError) as ex:
            # AttributeError/KeyError/TypeError guard against a malformed LFM track blob.
            _LOGGER.debug(f"{ex.__class__.__name__} during LFM track info resolution: {si}")
            if isinstance(ex, LFMRequestFailureException):
                si.lfm_request_failed = True
        mb_candidates: list[OriginRelease] = []
        try:
            if recording_mbid:
                mb_candidates = mb.lookup_recording_origin_releases(
                    recording_mbid=recording_mbid, artist_name=si.artist_name, artist_mbid=artist_mbid
                )
            # A capped lookup listing may have left out the original album; the search fills the gap (ranking dedupes
            # the overlap by release group).
            if len(mb_candidates) == 0 or len(mb_candidates) >= MUSICBRAINZ_LOOKUP_LINKED_ENTITY_CAP:
                mb_candidates = mb_candidates + mb.search_recording_origin_releases(
                    track_name=si.track_name, artist_name=si.artist_name, artist_mbid=artist_mbid
                )
        except MusicBrainzRequestFailureException as ex:
            _LOGGER.warning(f"{ex.__class__.__name__} during track origin release resolution: {si}: {ex}")
            si.mb_request_failed = True
        si.set_origin_candidates(rank_origin_candidates(mb_candidates=mb_candidates, lfm_candidate=lfm_candidate))
        if (top_origin := si.top_origin) is not None:
            _LOGGER.debug(
                f"Resolved {len(si.origin_candidates)} candidate origin release(s) for track '{si.track_name}' by "
                f"'{si.artist_name}'; top candidate: '{top_origin.release_name}' ({top_origin.source})."
            )
            upsert_resolved_origin(
                search_id=si.search_id,
                origin=top_origin,
                candidate_rank=0,
                candidate_count=len(si.origin_candidates),
                matched=False,
            )
        return si


class AttachSearchIdModifier(SearchItemModifier):
    """Creates the `SearchRecord` DB row for to the given `SearchItem`, and adds the record ID to the `SearchItem`."""

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        if si.is_manual:
            _LOGGER.debug("Manual search records are pre-initialized, skipping initialization.")
            return si
        search_record = SearchRecord.from_search_item(si=si)
        add_record(model_inst=search_record)
        si.search_id = search_record.id
        return si


def _request_release_details_with_fallback(
    si: SearchItem, mb: MusicBrainzAPIClient, mbid: str | None
) -> dict[str, Any] | None:
    """
    The MB release details for `mbid` when one is known and MB still serves it. Otherwise (no MBID, or a stale one MB
    answers with an error) an MBID is resolved via the MB release search first — its Lucene scoring tolerates minor
    naming differences, unlike an exact lookup. Returns `None` when no release could be resolved. Raises
    `MusicBrainzRequestFailureException` on a transport failure / unusable payload and `MusicBrainzClientException`
    on an error response for a searched MBID.
    """
    if mbid:
        try:
            return mb.request_release_details(mbid=mbid)
        except MusicBrainzClientException as ex:
            if isinstance(ex, MusicBrainzRequestFailureException):
                raise
            _LOGGER.info(f"MB does not serve release MBID '{mbid}' for '{si}'; resolving one via the release search.")
    searched_mbid = mb.search_release_mbid(artist_name=si.artist_name, release_name=si.release_name)
    if not searched_mbid:
        return None
    return mb.request_release_details(mbid=searched_mbid)


class AttemptResolveMBReleaseModifier(SearchItemModifier):
    """Intended as replacement for `ReleaseSearcher._attempt_resolve_mb_release`."""

    name = "AttemptResolveMBReleaseModifier"

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        # Skip the MusicBrainz release lookup entirely when its result would never be used (see
        # `SearchState.mb_resolution_would_be_used`).
        if not state.mb_resolution_would_be_used(si=si):
            _LOGGER.debug("MusicBrainz release resolution not required; skipping the lookup.")
            return si
        try:
            mb_release_json = _request_release_details_with_fallback(si=si, mb=mb, mbid=si.get_matched_mbid())
        except MusicBrainzRequestFailureException:
            _LOGGER.error(f"Musicbrainz request failure for search item '{si}'.", exc_info=True)
            si.mb_request_failed = True
            return si
        except MusicBrainzClientException:
            _LOGGER.error(f"Musicbrainz resolution error for search item '{si}'.", exc_info=True)
            return si
        if mb_release_json is None:
            _LOGGER.debug(f"No MB release resolved for artist: '{si.artist_name}', release: '{si.release_name}'")
            return si
        try:
            si.set_mb_release(MBRelease.construct_from_api(json_blob=mb_release_json))
        except KeyError:
            _LOGGER.error(f"Malformed Musicbrainz release payload for search item '{si}'.", exc_info=True)
        return si


class SearchRedReleaseByPrefsModifier(SearchItemModifier):
    """Intended as replacement for `ReleaseSearcher._search_red_release_by_preferences`."""

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        # Issue at most one artist-endpoint request per artist per run and do all release matching client-side: the
        # wanted title (plus year/release-type filters and label/catalogue-number ranking) selects the candidate
        # groups (`SearchState.get_candidate_release_groups`), then the candidates' torrents are ranked against the
        # format preferences (`SearchState.select_best_torrent`). A track item tries each of its origin candidates in
        # turn (`SearchState.match_track_origin_candidates`).
        artist_name = si.artist_name
        release_entries = state.get_cached_artist_release_groups(artist_name=artist_name)
        if release_entries is None:
            try:
                release_entries = red.get_artist_release_groups(artist_name=artist_name)
                # Cache the fetched listing (empty included) for later recs by the same artist this run. The
                # exception path is deliberately NOT cached, so a transient request failure doesn't turn every
                # later rec by the artist into a silent no-match.
                state.cache_artist_release_groups(artist_name=artist_name, release_entries=release_entries)
            except Exception:
                _LOGGER.error(f"RED artist request failed for artist '{artist_name}': ", exc_info=True)
                release_entries = []
        else:
            _LOGGER.debug(f"Using this run's cached RED release-group listing for artist '{artist_name}'.")
        if si.origin_candidates:
            torrent_match = state.match_track_origin_candidates(si=si, release_entries=release_entries)
        else:
            candidate_entries = state.get_candidate_release_groups(si=si, release_entries=release_entries)
            torrent_match = state.select_best_torrent(release_entries=candidate_entries)
        if torrent_match.torrent_entry is None:
            _LOGGER.debug(f"No torrent match found for si: {si.initial_info}")
        elif (matched_origin := si.matched_origin) is not None:
            upsert_resolved_origin(
                search_id=si.search_id,
                origin=matched_origin,
                candidate_rank=si.origin_candidates.index(matched_origin),
                candidate_count=len(si.origin_candidates),
                matched=True,
            )
        si.set_torrent_match_fields(torrent_match=torrent_match)
        return si
