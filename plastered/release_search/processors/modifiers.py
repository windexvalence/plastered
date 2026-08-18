"""Implementations of the `SearchItemModifier` abstract base class should live in this file."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plastered.db.db_models import SearchRecord
from plastered.db.db_utils import add_record
from plastered.models import LFMAlbumInfo, LFMTrackInfo, MBRelease
from plastered.release_search.processors.bases import SearchItemModifier
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


class ResolveTrackInfoModifier(SearchItemModifier):
    """Intended as replacement for `ReleaseSearcher._resolve_lfm_track_info`."""

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        lfm_resp: dict[str, Any] | None = None
        try:
            if (lfm_resp := lfm.get_track_info(si=si)) and "album" in lfm_resp:
                si.set_lfm_track_info(LFMTrackInfo.construct_from_api_response(json_blob=lfm_resp))
                return si
        except (LFMClientException, KeyError, TypeError) as ex:
            # KeyError/TypeError guard against a malformed LFM `album` blob; fall through to MusicBrainz resolution.
            _LOGGER.debug(f"{ex.__class__.__name__} during track origin release resolution: {si}")
            if isinstance(ex, LFMRequestFailureException):
                si.lfm_request_failed = True
        artist_mbid = None
        if isinstance(lfm_resp, dict) and isinstance(lfm_resp.get("artist"), dict):
            artist_mbid = lfm_resp["artist"].get("mbid")
        try:
            if origin_info := mb.request_release_details_for_track(si=si, artist_mbid=artist_mbid):
                si.set_lfm_track_info(
                    lfmti=LFMTrackInfo.from_mb_origin_release_info(si=si, origin_info_json=origin_info)
                )
        except MusicBrainzRequestFailureException as ex:
            _LOGGER.warning(f"{ex.__class__.__name__} during track origin release resolution: {si}: {ex}")
            si.mb_request_failed = True
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


class AttemptResolveMBReleaseModifier(SearchItemModifier):
    """Intended as replacement for `ReleaseSearcher._attempt_resolve_mb_release`."""

    name = "AttemptResolveMBReleaseModifier"

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        # Skip the MusicBrainz release lookup entirely when its result would never be used: the scraper flow only needs
        # the MB release details to populate optional RED search fields, so when none are enabled we save the call.
        if not state.mb_resolution_would_be_used(si=si):
            _LOGGER.debug("MusicBrainz release resolution not required by config; skipping the lookup.")
            return si
        mbid = si.get_matched_mbid()
        if not mbid:
            # LFM's MBID coverage is sparse and stale, so fall back to resolving one via the MB release search — its
            # Lucene scoring tolerates minor naming differences, unlike an exact lookup.
            try:
                mbid = mb.search_release_mbid(artist_name=si.artist_name, release_name=si.release_name)
            except MusicBrainzRequestFailureException:
                _LOGGER.error(f"Musicbrainz request failure during release search for '{si}'.", exc_info=True)
                si.mb_request_failed = True
                return si
        if not mbid:
            _LOGGER.debug(f"No MBID resolved for artist: '{si.artist_name}', release: '{si.release_name}'")
            return si
        try:
            si.set_mb_release(MBRelease.construct_from_api(json_blob=mb.request_release_details(mbid=mbid)))
        except MusicBrainzRequestFailureException:
            _LOGGER.error(f"Musicbrainz request failure for search item '{si}'.", exc_info=True)
            si.mb_request_failed = True
        except MusicBrainzClientException, KeyError:
            _LOGGER.error(f"Musicbrainz resolution error for search item '{si}'.", exc_info=True)
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
        # format preferences (`SearchState.select_best_torrent`).
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
        candidate_entries = state.get_candidate_release_groups(si=si, release_entries=release_entries)
        torrent_match = state.select_best_torrent(release_entries=candidate_entries)
        if torrent_match.torrent_entry is None:
            _LOGGER.debug(f"No torrent match found for si: {si.initial_info}")
        si.set_torrent_match_fields(torrent_match=torrent_match)
        return si
