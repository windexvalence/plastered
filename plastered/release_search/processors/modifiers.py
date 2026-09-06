"""Implementations of the `SearchItemModifier` abstract base class should live in this file."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plastered.db.db_models import SearchRecord
from plastered.db.db_utils import add_record, upsert_resolved_origin
from plastered.models import (
    LFMAlbumInfo,
    MBRelease,
    OriginRelease,
    RedReleaseType,
    SearchStage,
    SearchStepOutcome,
    counted,
    origin_label,
    quoted,
    rank_origin_candidates,
    release_type_name,
)
from plastered.release_search.processors.bases import SearchItemModifier
from plastered.utils.constants import MUSICBRAINZ_LOOKUP_LINKED_ENTITY_CAP
from plastered.utils.exceptions import (
    LFMClientException,
    LFMRequestFailureException,
    MusicBrainzClientException,
    MusicBrainzRequestFailureException,
)

if TYPE_CHECKING:
    from plastered.models import ReleaseEntry, SearchItem
    from plastered.release_search.search_helpers import SearchState
    from plastered.utils.http_clients import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient

_LOGGER = logging.getLogger(__name__)
# How many of a track's candidate origin releases the trace lists by name.
_TRACED_ORIGIN_CANDIDATES_CAP = 5
_VIA_MBID_LOOKUP = "MBID lookup"
_VIA_RELEASE_SEARCH = "release search"


def _lfm_failure_detail(ex: Exception, lookup: str) -> str:
    """The trace detail of a failed LFM `lookup` ("album" / "track")."""
    if isinstance(ex, LFMRequestFailureException):
        return "Last.fm request failed"
    if isinstance(ex, LFMClientException):
        return f"Last.fm {lookup} lookup failed: {ex}"
    return f"Last.fm returned an unusable {lookup} payload"


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
            outcome = SearchStepOutcome.OK
            detail = (
                f"Last.fm album info found (release MBID {quoted(lfmai.release_mbid)})"
                if lfmai.release_mbid
                else "Last.fm album info found (no release MBID)"
            )
        except LFMClientException as ex:
            _LOGGER.debug(f"{ex.__class__.__name__} during LFM album info resolution for search item: {si}")
            if isinstance(ex, LFMRequestFailureException):
                si.lfm_request_failed = True
            lfmai = None
            outcome = SearchStepOutcome.WARNING
            detail = _lfm_failure_detail(ex=ex, lookup="album")
        si.set_lfm_album_info(lfmai=lfmai)
        si.add_trace_step(stage=SearchStage.LFM_ALBUM_INFO, outcome=outcome, detail=detail)
        return si


def _describe_origin_candidates(candidates: list[OriginRelease]) -> str:
    """`3 candidate origin releases, best first: "A" (album, 1996), ...`, naming at most the top few."""
    labels = [origin_label(candidate) for candidate in candidates[:_TRACED_ORIGIN_CANDIDATES_CAP]]
    text = f"{counted(len(candidates), 'candidate origin release')}, best first: {', '.join(labels)}"
    if len(candidates) > _TRACED_ORIGIN_CANDIDATES_CAP:
        text += f", … and {len(candidates) - _TRACED_ORIGIN_CANDIDATES_CAP} more"
    return text


class ResolveTrackOriginModifier(SearchItemModifier):
    """
    Resolves a track item's candidate origin releases, ranked best-first (see `rank_origin_candidates`): the release
    LFM associates with the track plus every release MusicBrainz lists for the recording — via the recording lookup
    when LFM supplies the recording MBID, and via the recording search when it doesn't or when the lookup is capped or
    lists no release a track can originate from (`OriginRelease.is_track_origin_type`: a stale MBID, an artist
    mismatch, or an MBID naming e.g. a live take that only appears on live albums) — keeping only the albums / EPs /
    singles / soundtracks and the releases of unknown type among them. The top candidate becomes `si.release_name`
    and is persisted as the item's resolved origin (see `upsert_resolved_origin`).
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
            si.add_trace_step(
                stage=SearchStage.LFM_TRACK_INFO,
                outcome=SearchStepOutcome.OK if lfm_candidate is not None else SearchStepOutcome.WARNING,
                detail=(
                    f"Last.fm lists the track on {quoted(lfm_candidate.release_name)}"
                    if lfm_candidate is not None
                    else "Last.fm lists no release for the track"
                ),
            )
        except (LFMClientException, AttributeError, KeyError, TypeError) as ex:
            # AttributeError/KeyError/TypeError guard against a malformed LFM track blob.
            _LOGGER.debug(f"{ex.__class__.__name__} during LFM track info resolution: {si}")
            if isinstance(ex, LFMRequestFailureException):
                si.lfm_request_failed = True
            si.add_trace_step(
                stage=SearchStage.LFM_TRACK_INFO,
                outcome=SearchStepOutcome.WARNING,
                detail=_lfm_failure_detail(ex=ex, lookup="track"),
            )
        mb_candidates: list[OriginRelease] = []
        lookups: list[str] = []
        try:
            if recording_mbid:
                lookups.append("recording lookup by MBID")
                mb_candidates = mb.lookup_recording_origin_releases(
                    recording_mbid=recording_mbid, artist_name=si.artist_name, artist_mbid=artist_mbid
                )
            # The search fills the gap when the lookup listed no release a track can originate from (ranking would
            # drop every listed one) or when its capped listing may have left out the original album; ranking
            # dedupes the overlap by release group.
            has_origin_type_release = any(candidate.is_track_origin_type for candidate in mb_candidates)
            if not has_origin_type_release or len(mb_candidates) >= MUSICBRAINZ_LOOKUP_LINKED_ENTITY_CAP:
                lookups.append("recording search")
                mb_candidates = mb_candidates + mb.search_recording_origin_releases(
                    track_name=si.track_name, artist_name=si.artist_name, artist_mbid=artist_mbid
                )
        except MusicBrainzRequestFailureException as ex:
            _LOGGER.warning(f"{ex.__class__.__name__} during track origin release resolution: {si}: {ex}")
            si.mb_request_failed = True
            si.add_trace_step(
                stage=SearchStage.MB_RECORDING,
                outcome=SearchStepOutcome.WARNING,
                detail=f"MusicBrainz request failed ({' + '.join(lookups)})",
            )
        else:
            via = " + ".join(lookups)
            # The search gathers the releases of every recording of the track, not just LFM's.
            listed_for = "the recording" if lookups == ["recording lookup by MBID"] else "recordings of the track"
            si.add_trace_step(
                stage=SearchStage.MB_RECORDING,
                outcome=SearchStepOutcome.OK if mb_candidates else SearchStepOutcome.WARNING,
                detail=(
                    f"MusicBrainz lists {counted(len(mb_candidates), 'release')} for {listed_for} ({via})"
                    if mb_candidates
                    else f"MusicBrainz lists no release for a recording of {quoted(si.track_name)} by "
                    f"{quoted(si.artist_name)} ({via})"
                ),
            )
        si.set_origin_candidates(rank_origin_candidates(mb_candidates=mb_candidates, lfm_candidate=lfm_candidate))
        gathered = bool(mb_candidates) or lfm_candidate is not None
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
            si.add_trace_step(
                stage=SearchStage.TRACK_ORIGIN,
                outcome=SearchStepOutcome.OK,
                detail=_describe_origin_candidates(candidates=si.origin_candidates),
            )
        elif gathered:
            si.add_trace_step(
                stage=SearchStage.TRACK_ORIGIN,
                outcome=SearchStepOutcome.WARNING,
                detail="None of the gathered releases is an album / EP / single / soundtrack",
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
) -> tuple[dict[str, Any] | None, str]:
    """
    The MB release details for `mbid` when one is known and MB still serves it. Otherwise (no MBID, or a stale one MB
    answers with an error) an MBID is resolved via the MB release search first — its Lucene scoring tolerates minor
    naming differences, unlike an exact lookup. Returns the details (`None` when no release could be resolved) and
    how the MBID was obtained (`_VIA_MBID_LOOKUP` / `_VIA_RELEASE_SEARCH`). Raises
    `MusicBrainzRequestFailureException` on a transport failure / unusable payload and `MusicBrainzClientException`
    on an error response for a searched MBID.
    """
    if mbid:
        try:
            return mb.request_release_details(mbid=mbid), _VIA_MBID_LOOKUP
        except MusicBrainzClientException as ex:
            if isinstance(ex, MusicBrainzRequestFailureException):
                raise
            _LOGGER.info(f"MB does not serve release MBID '{mbid}' for '{si}'; resolving one via the release search.")
            si.add_trace_step(
                stage=SearchStage.MB_RELEASE,
                outcome=SearchStepOutcome.WARNING,
                detail=f"MusicBrainz does not serve release MBID {quoted(mbid)}; searching for the release instead",
            )
    searched_mbid = mb.search_release_mbid(artist_name=si.artist_name, release_name=si.release_name)
    if not searched_mbid:
        return None, _VIA_RELEASE_SEARCH
    return mb.request_release_details(mbid=searched_mbid), _VIA_RELEASE_SEARCH


def _describe_mb_release(mbr: MBRelease, via: str) -> str:
    """`Resolved MusicBrainz release "T" (MBID m, via MBID lookup): type album, year 1996, ...` (known fields only)."""
    fields: list[str] = []
    if (red_release_type := mbr.get_red_release_type()) != RedReleaseType.UNKNOWN:
        fields.append(f"type {release_type_name(red_release_type)}")
    if (mbr.first_release_year or 0) > 0:
        fields.append(f"year {mbr.first_release_year}")
    if mbr.label:
        fields.append(f"label {quoted(mbr.label)}")
    if mbr.catalog_number:
        fields.append(f"catalogue number {quoted(mbr.catalog_number)}")
    text = f"Resolved MusicBrainz release {quoted(mbr.title)} (MBID {mbr.mbid}, via {via})"
    return f"{text}: {', '.join(fields) if fields else 'no release type, year, label or catalogue number'}"


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
            mb_release_json, via = _request_release_details_with_fallback(si=si, mb=mb, mbid=si.get_matched_mbid())
        except MusicBrainzRequestFailureException:
            _LOGGER.error(f"Musicbrainz request failure for search item '{si}'.", exc_info=True)
            si.mb_request_failed = True
            _trace_unresolved_mb_release(si=si, detail="MusicBrainz request failed")
            return si
        except MusicBrainzClientException:
            _LOGGER.error(f"Musicbrainz resolution error for search item '{si}'.", exc_info=True)
            _trace_unresolved_mb_release(si=si, detail="MusicBrainz returned an error for the release")
            return si
        if mb_release_json is None:
            _LOGGER.debug(f"No MB release resolved for artist: '{si.artist_name}', release: '{si.release_name}'")
            _trace_unresolved_mb_release(
                si=si, detail=f"No MusicBrainz release found for {quoted(si.release_name)} by {quoted(si.artist_name)}"
            )
            return si
        try:
            mb_release = MBRelease.construct_from_api(json_blob=mb_release_json)
        except KeyError:
            _LOGGER.error(f"Malformed Musicbrainz release payload for search item '{si}'.", exc_info=True)
            _trace_unresolved_mb_release(si=si, detail="Malformed MusicBrainz release payload")
            return si
        si.set_mb_release(mb_release)
        si.add_trace_step(
            stage=SearchStage.MB_RELEASE,
            outcome=SearchStepOutcome.OK,
            detail=_describe_mb_release(mbr=mb_release, via=via),
        )
        return si


def _trace_unresolved_mb_release(si: SearchItem, detail: str) -> None:
    si.add_trace_step(
        stage=SearchStage.MB_RELEASE,
        outcome=SearchStepOutcome.WARNING,
        detail=f"{detail}; continuing without release details",
    )


def _artist_release_groups(si: SearchItem, state: SearchState, red: RedAPIClient) -> list[ReleaseEntry]:
    """
    The artist's RED release groups: this run's cached listing, else fetched now (and cached for later recs by the
    artist this run). The lookup is traced on the item. A failed request yields an empty listing and is deliberately
    NOT cached, so a transient failure doesn't turn every later rec by the artist into a silent no-match.
    """
    artist_name = si.artist_name
    release_entries = state.get_cached_artist_release_groups(artist_name=artist_name)
    if release_entries is not None:
        _LOGGER.debug(f"Using this run's cached RED release-group listing for artist '{artist_name}'.")
    else:
        try:
            release_entries = red.get_artist_release_groups(artist_name=artist_name)
        except Exception:
            _LOGGER.error(f"RED artist request failed for artist '{artist_name}': ", exc_info=True)
            si.add_trace_step(
                stage=SearchStage.RED_ARTIST,
                outcome=SearchStepOutcome.WARNING,
                detail=f"RED artist request failed for artist {quoted(artist_name)}",
            )
            return []
        # An empty listing is cached too: an artist RED doesn't know stays unknown for the whole run.
        state.cache_artist_release_groups(artist_name=artist_name, release_entries=release_entries)
    si.add_trace_step(
        stage=SearchStage.RED_ARTIST,
        outcome=SearchStepOutcome.OK if release_entries else SearchStepOutcome.WARNING,
        detail=(
            f"RED lists {counted(len(release_entries), 'release group')} for artist {quoted(artist_name)}"
            if release_entries
            else f"RED lists no release groups for artist {quoted(artist_name)}"
        ),
    )
    return release_entries


class SearchRedReleaseByPrefsModifier(SearchItemModifier):
    """Intended as replacement for `ReleaseSearcher._search_red_release_by_preferences`."""

    @staticmethod
    def process(
        si: SearchItem, state: SearchState, lfm: LFMAPIClient, mb: MusicBrainzAPIClient, red: RedAPIClient
    ) -> SearchItem:
        # Issue at most one artist-endpoint request per artist per run and do all release matching client-side: the
        # wanted title (plus year/release-type filters and label/catalogue-number ranking) selects the candidate
        # groups, then the candidates' torrents are ranked against the format preferences
        # (`SearchState.match_album_release`). A track item tries each of its origin candidates in turn
        # (`SearchState.match_track_origin_candidates`).
        release_entries = _artist_release_groups(si=si, state=state, red=red)
        if si.origin_candidates:
            torrent_match = state.match_track_origin_candidates(si=si, release_entries=release_entries)
        else:
            torrent_match = state.match_album_release(si=si, release_entries=release_entries)
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
