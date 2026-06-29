"""Implementations of the `SearchItemModifier` abstract base class should live in this file."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plastered.db.db_models import SearchRecord
from plastered.db.db_utils import add_record
from plastered.models import LFMAlbumInfo, LFMTrackInfo, MBRelease, TorrentMatch
from plastered.release_search.processors.bases import SearchItemModifier
from plastered.utils.exceptions import LFMClientException, MusicBrainzClientException

if TYPE_CHECKING:
    from plastered.models import ReleaseEntry, SearchItem
    from plastered.release_search.search_helpers import SearchState
    from plastered.utils.httpx_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient

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
        except LFMClientException as ex:  # pragma: no cover
            _LOGGER.debug(f"{ex.__class__.__name__} during LFM album info resolution for search item: {si}")
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
        artist_mbid = None
        if isinstance(lfm_resp, dict) and isinstance(lfm_resp.get("artist"), dict):
            artist_mbid = lfm_resp["artist"].get("mbid")
        if origin_info := mb.request_release_details_for_track(si=si, artist_mbid=artist_mbid):
            si.set_lfm_track_info(lfmti=LFMTrackInfo.from_mb_origin_release_info(si=si, origin_info_json=origin_info))
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
        if not (mbid := si.get_matched_mbid()):
            _LOGGER.debug(f"No MBID to resolve from for artist: '{si.artist_name}', release: '{si.release_name}'")
            return si
        try:
            si.set_mb_release(MBRelease.construct_from_api(json_blob=mb.request_release_details(mbid=mbid)))
        except (MusicBrainzClientException, KeyError):
            _LOGGER.error(f"Musicbrainz resolution error for search item '{si}'.", exc_info=True)
        return si


class SearchRedReleaseByPrefsModifier(SearchItemModifier):
    """Intended as replacement for `ReleaseSearcher._search_red_release_by_preferences`."""

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        torrent_match: TorrentMatch | None = None
        for pref in state.red_format_preferences:
            # Build params outside the try so a browse failure's log line can't hit an unassigned `req_params`.
            req_params = state.create_red_browse_params(red_format=pref, si=si)
            try:
                release_entries = red.browse(request_params=req_params)
            except Exception:
                _LOGGER.error(f"RED browse request failed: {req_params}: ", exc_info=True)
                continue
            if not (
                torrent_match := SearchRedReleaseByPrefsModifier._torrent_match_from_browse_results(
                    browse_results=release_entries, state=state
                )
            ).above_max_size_found:
                break

        if not torrent_match:
            _LOGGER.debug(f"No torrent match found for si: {si.initial_info}")
            torrent_match = TorrentMatch(torrent_entry=None, above_max_size_found=False)

        si.set_torrent_match_fields(torrent_match=torrent_match)
        return si

    @staticmethod
    def _torrent_match_from_browse_results(browse_results: list[ReleaseEntry], state: SearchState) -> TorrentMatch:
        above_max_size_found = False
        for release_entry in browse_results:
            for torrent_entry in release_entry.get_torrent_entries():
                if torrent_entry.get_size(unit="GB") <= state.max_size_gb:
                    return TorrentMatch(torrent_entry=torrent_entry, above_max_size_found=False)
                else:
                    above_max_size_found = True
        return TorrentMatch(torrent_entry=None, above_max_size_found=above_max_size_found)
