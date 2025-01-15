import logging
import os
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from plastered.config.config_parser import AppConfig
from plastered.run_cache.run_cache import CacheType, RunCache
from plastered.scraper.lfm_scraper import LFMRec, RecContext
from plastered.stats.stats import (
    SkippedReason,
    SnatchFailureReason,
    print_and_save_all_searcher_stats,
)
from plastered.utils.exceptions import ReleaseSearcherException
from plastered.utils.http_utils import LFMAPIClient, MusicBrainzAPIClient, RedAPIClient
from plastered.utils.lfm_utils import LFMAlbumInfo
from plastered.utils.musicbrainz_utils import MBRelease
from plastered.utils.red_utils import (
    RedFormat,
    RedUserDetails,
    ReleaseEntry,
    TorrentEntry,
)

_LOGGER = logging.getLogger(__name__)

_SUMMARY_TSV_HEADER = [
    "entity_type",
    "rec_context",
    "lfm_entity_url",
    "red_permalink",
    "snatch_path",
    "release_mbid",
]


def require_mbid_resolution(
    use_release_type: bool, use_first_release_year: bool, use_record_label: bool, use_catalog_number: bool
) -> bool:
    return use_release_type or use_first_release_year or use_record_label or use_catalog_number


class ReleaseSearcher:
    """
    General 'brains' for searching for a collection of LFM-recommended releases.
    Responsible for ultimately searching, filtering, and downloading matching releases from RED.
    Optionally may interact with the official LFM API to collect the MBID for a release, and may also optionally
    interact with the official MusicBrainz API to gather more specific search parameters to use on the RED browse endpoint.
    """

    def __init__(self, app_config: AppConfig):
        self._red_user_id = app_config.get_cli_option("red_user_id")
        self._red_user_details: Optional[RedUserDetails] = None
        self._skip_prior_snatches = app_config.get_cli_option("skip_prior_snatches")
        self._allow_library_items = app_config.get_cli_option("allow_library_items")
        self._output_summary_filepath_prefix = app_config.get_output_summary_filepath_prefix()
        self._enable_snatches = app_config.get_cli_option("snatch_recs")
        self._snatch_directory = app_config.get_cli_option("snatch_directory")
        self._use_release_type = app_config.get_cli_option("use_release_type")
        self._use_first_release_year = app_config.get_cli_option("use_first_release_year")
        self._use_record_label = app_config.get_cli_option("use_record_label")
        self._use_catalog_number = app_config.get_cli_option("use_catalog_number")
        self._require_mbid_resolution = require_mbid_resolution(
            use_release_type=self._use_release_type,
            use_first_release_year=self._use_first_release_year,
            use_record_label=self._use_record_label,
            use_catalog_number=self._use_catalog_number,
        )
        self._run_cache = RunCache(app_config=app_config, cache_type=CacheType.API)
        self._red_client = RedAPIClient(app_config=app_config, run_cache=self._run_cache)

        if self._require_mbid_resolution:
            self._lfm_client = LFMAPIClient(app_config=app_config, run_cache=self._run_cache)
            self._musicbrainz_client = MusicBrainzAPIClient(app_config=app_config, run_cache=self._run_cache)
        else:
            self._lfm_client = None
            self._musicbrainz_client = None
        self._red_format_preferences = app_config.get_red_preference_ordering()
        self._max_size_gb = app_config.get_cli_option("max_size_gb")
        self._tsv_output_summary_rows = []
        self._snatch_summary_rows: List[List[str]] = []
        self._skipped_snatch_summary_rows: List[List[str]] = []
        self._failed_snatches_summary_rows: List[List[str]] = []
        self._torrent_entries_to_snatch: List[TorrentEntry] = []

    def gather_red_user_details(self) -> None:
        _LOGGER.info(f"Gathering red user details to help with search filtering ...")
        user_stats_json = self._red_client.request_api(action="community_stats", params=f"userid={self._red_user_id}")
        snatched_torrent_count = int(user_stats_json["snatched"].replace(",", ""))
        user_torrents_json = self._red_client.request_api(
            action="user_torrents",
            params=f"id={self._red_user_id}&type=snatched&limit={snatched_torrent_count}&offset=0",
        )
        self._red_user_details = RedUserDetails(
            user_id=self._red_user_id,
            snatched_count=snatched_torrent_count,
            snatched_torrents_list=user_torrents_json["snatched"],
        )

    def _add_skipped_snatch_row(self, rec: LFMRec, reason: SkippedReason) -> None:
        self._skipped_snatch_summary_rows.append(
            [
                rec.rec_type.value,
                rec.rec_context.value,
                rec.get_human_readable_artist_str(),
                rec.get_human_readable_entity_str(),
                reason.value,
            ]
        )

    def _add_failed_snatch_row(self, te: TorrentEntry, exception_class_name: str) -> None:
        snatch_failure_reason = SnatchFailureReason.OTHER
        if (
            exception_class_name == SnatchFailureReason.RED_API_REQUEST_ERROR
            or exception_class_name == SnatchFailureReason.FILE_ERROR
        ):
            snatch_failure_reason = SnatchFailureReason(exception_class_name)
        self._failed_snatches_summary_rows.append(
            [te.get_permalink_url(), te.get_matched_mbid(), snatch_failure_reason.value]
        )

    def _add_snatch_row(self, te: TorrentEntry, snatch_path: str) -> None:
        self._snatch_summary_rows.append(
            [
                te.get_lfm_rec_type(),
                te.get_lfm_rec_context(),
                te.get_artist_name(),
                te.get_release_name(),
                te.torrent_id,
                te.media,
                "yes" if self._red_client.tid_snatched_with_fl_token(tid=te.torrent_id) else "no",
                snatch_path,
            ],
        )
        pass  # TODO:

    # pylint: disable=redefined-builtin
    def create_red_browse_params(self, red_format: RedFormat, lfm_rec: LFMRec, **search_kwargs) -> str:
        """Utility method for creating the RED browse API params string"""
        artist_name = lfm_rec.artist_str
        album_name = lfm_rec.entity_str
        format = red_format.get_format()
        encoding = red_format.get_encoding()
        media = red_format.get_media()
        # TODO: figure out why the `order_by` param appears to be ignored whenever the params also have `group_results=1`.
        browse_request_params = f"artistname={artist_name}&groupname={album_name}&format={format}&encoding={encoding}&media={media}&group_results=1&order_by=seeders&order_way=desc"
        release_type = search_kwargs.get("release_type") if self._use_release_type else None
        first_release_year = search_kwargs.get("first_release_year") if self._use_first_release_year else None
        record_label = search_kwargs.get("record_label") if self._use_record_label else None
        catalog_number = search_kwargs.get("catalog_number") if self._use_catalog_number else None
        if release_type:
            browse_request_params += f"&releasetype={release_type.value}"
        if first_release_year:
            browse_request_params += f"&year={first_release_year}"
        if record_label:
            browse_request_params += f"&recordlabel={quote_plus(record_label)}"
        if catalog_number:
            browse_request_params += f"&cataloguenumber={quote_plus(catalog_number)}"
        return browse_request_params

    def _search_red_release_by_preferences(self, lfm_rec: LFMRec, **search_kwargs) -> Optional[TorrentEntry]:
        above_max_size_found = False
        for pref in self._red_format_preferences:
            browse_request_params = self.create_red_browse_params(
                red_format=pref, lfm_rec=lfm_rec, search_kwargs=search_kwargs
            )
            try:
                red_browse_response = self._red_client.request_api(action="browse", params=browse_request_params)
            except Exception:
                _LOGGER.error(f"Uncaught exception during RED browse request: {browse_request_params}: ", exc_info=True)
                continue
            release_entries_browse_response = [
                ReleaseEntry.from_torrent_search_json_blob(json_blob=result_blob)
                for result_blob in red_browse_response["results"]
            ]

            # Find best torrent entry
            for release_entry in release_entries_browse_response:
                for torrent_entry in release_entry.get_torrent_entries():
                    size_gb = torrent_entry.get_size(unit="GB")
                    if size_gb <= self._max_size_gb:
                        return torrent_entry
                    above_max_size_found = True
        skip_reason = SkippedReason.ABOVE_MAX_SIZE if above_max_size_found else SkippedReason.NO_MATCH_FOUND
        self._add_skipped_snatch_row(rec=lfm_rec, reason=skip_reason)
        return None

    def _resolve_lfm_album_info(self, lfm_rec: LFMRec) -> LFMAlbumInfo:
        return LFMAlbumInfo.construct_from_api_response(
            json_blob=self._lfm_client.request_api(
                method="album.getinfo",
                params=f"artist={lfm_rec.artist_str}&album={lfm_rec.entity_str}",
            )
        )

    def _resolve_mb_release(self, mbid: str) -> MBRelease:
        return MBRelease.construct_from_api(
            json_blob=self._musicbrainz_client.request_api(entity_type="release", mbid=mbid)
        )

    def _pre_search_filter_validate(self, lfm_rec: LFMRec) -> bool:
        """
        Return True if the lfm_rec is valid to search for on the various APIs, or False if the lfm_rec should be skipped given the current app config settings.
        """
        artist = lfm_rec.get_human_readable_artist_str()
        album = lfm_rec.get_human_readable_entity_str()
        if self._skip_prior_snatches and self._red_user_details.has_snatched_release(artist=artist, album=album):
            _LOGGER.debug(f"'skip_prior_snatches' config field is set to True")
            _LOGGER.debug(f"Skipped - artist: '{artist}', album: '{album}' due to prior snatch found in release group")
            self._add_skipped_snatch_row(rec=lfm_rec, reason=SkippedReason.ALREADY_SNATCHED)
            return False
        if not self._allow_library_items and lfm_rec.rec_context == RecContext.IN_LIBRARY:
            _LOGGER.debug(f"'allow_library_items' config field is set to {self._allow_library_items}.")
            _LOGGER.debug(
                f"Skipped - artist: '{artist}', album: '{album}'. Rec context is {RecContext.IN_LIBRARY.value}"
            )
            self._add_skipped_snatch_row(rec=lfm_rec, reason=SkippedReason.REC_CONTEXT_FILTERING)
            return False
        return True

    # TODO: add logic for a `search_for_track_rec` that basically ends up just calling this
    def search_for_album_rec(self, lfm_rec: LFMRec) -> Optional[TorrentEntry]:
        """
        Searches for the recommended album, and returns a tuple containing the permalink for the best RED match
        and the release mbid (if an mbid is found / the app is configured to request an mbid from LFM's API)
        according to format_preferences, search preferences, and snatch preferences.
        Returns None if no viable match is found.
        """
        if not self._pre_search_filter_validate(lfm_rec=lfm_rec):
            return None
        artist = lfm_rec.get_human_readable_artist_str()
        album = lfm_rec.get_human_readable_entity_str()
        # If filtering the RED searches by any of these fields, then grab the release mbid from LFM, then hit musicbrainz to get the relevant data fields.
        release_mbid = None
        search_kwargs = {}
        if self._require_mbid_resolution:
            lfm_album_info = self._resolve_lfm_album_info(lfm_rec=lfm_rec)
            release_mbid = lfm_album_info.get_release_mbid()
            if release_mbid:
                _LOGGER.debug(
                    f"Attempting musicbrainz query for artist: {artist}, release: '{album}', release-mbid: '{release_mbid}'"
                )
                mb_release = self._resolve_mb_release(mbid=release_mbid)
                search_kwargs = mb_release.get_release_searcher_kwargs()
            else:  # pragma: no cover
                _LOGGER.debug(f"LFM gave no MBID for artist: '{artist}', release: '{album}'")

        best_torrent_entry = self._search_red_release_by_preferences(lfm_rec=lfm_rec, search_kwargs=search_kwargs)
        if best_torrent_entry:
            best_torrent_entry.set_matched_mbid(matched_mbid=release_mbid)
            best_torrent_entry.set_lfm_rec_fields(
                rec_type=lfm_rec.rec_type.value,
                rec_context=lfm_rec.rec_context.value,
                artist_name=artist,
                release_name=album,
            )
            return best_torrent_entry

        _LOGGER.warning(f"Could not find any valid search matches for artist: '{artist}', album: '{album}'")
        return None

    def _get_tid_and_snatch_path(self, permalink: str) -> Tuple[str, str]:
        tid = permalink.split("=")[-1]
        return tid, os.path.join(self._snatch_directory, f"{tid}.torrent")

    def search_for_album_recs(self, album_recs: List[LFMRec]) -> None:
        """
        Iterate over the list of album_recs and search for each one on RED.
        Returns the list of RED permalinks which match the search criteria for the given LFMRec.
        Optionally will save the .torrent files in the specified snatch directory.
        """
        if self._skip_prior_snatches and self._red_user_details is None:
            raise ReleaseSearcherException(
                f"self._skip_prior_snatches set to {self._skip_prior_snatches}, but self._red_user_details has not yet been populated."
            )
        # Required so that tqdm doesnt break logging: https://stackoverflow.com/a/69145493
        with logging_redirect_tqdm(loggers=[_LOGGER]):
            for album_rec in tqdm(album_recs, desc="Searching album recs"):
                matched_torrent_entry = self.search_for_album_rec(lfm_rec=album_rec)
                if not matched_torrent_entry:
                    continue
                permalink = matched_torrent_entry.get_permalink_url()
                cur_tsv_output_row = (
                    "album",
                    album_rec.rec_context.value,
                    album_rec.lfm_entity_url,
                    permalink,
                    self._get_tid_and_snatch_path(permalink=permalink)[1],
                    str(matched_torrent_entry.get_matched_mbid()),
                )
                self._tsv_output_summary_rows.append(cur_tsv_output_row)
                self._torrent_entries_to_snatch.append(matched_torrent_entry)
        if self._run_cache.enabled:
            self._run_cache.close()

    def snatch_matches(self) -> None:
        if not self._enable_snatches:
            _LOGGER.warning(f"Not configured to snatch. Please update your config to enable.")
            return
        _LOGGER.debug(f"Beginning to snatch matched permalinks to download directory '{self._snatch_directory}' ...")
        # Prepare a list of to-snatch torrents in descending size to ensure FL tokens are used optimally (if FL token usage is enabled).
        to_snatch = sorted(self._torrent_entries_to_snatch, key=lambda te: te.get_size(unit="MB"), reverse=True)
        # Required so that tqdm doesnt break logging: https://stackoverflow.com/a/69145493
        with logging_redirect_tqdm(loggers=[_LOGGER]):
            for torrent_entry_to_snatch in tqdm(to_snatch, desc="Snatching matched torrents"):
                permalink = torrent_entry_to_snatch.get_permalink_url()
                tid, out_filepath = self._get_tid_and_snatch_path(permalink=permalink)
                _LOGGER.debug(f"Snatching {permalink} and saving to {out_filepath} ...")
                failed_snatch = False
                try:
                    binary_contents = self._red_client.snatch(
                        tid=tid,
                        can_use_token_on_torrent=torrent_entry_to_snatch.token_usable(),
                    )
                    with open(out_filepath, "wb") as f:
                        f.write(binary_contents)
                except Exception as ex:
                    failed_snatch = True
                    # Delete any potential file artifacts in case the failure took place in the middle of the .torrent file writing.
                    if os.path.exists(out_filepath):
                        os.remove(out_filepath)
                    _LOGGER.error(
                        f"Failed to snatch - uncaught error during snatch attempt for: {permalink}: ", exc_info=True
                    )
                    self._add_failed_snatch_row(te=torrent_entry_to_snatch, exception_class_name=ex.__class__.__name__)
                if not failed_snatch:
                    self._add_snatch_row(te=torrent_entry_to_snatch, snatch_path=out_filepath)

    def generate_summary_stats(self) -> None:
        print_and_save_all_searcher_stats(
            skipped_rows=self._skipped_snatch_summary_rows,
            failed_snatch_rows=self._failed_snatches_summary_rows,
            snatch_summary_rows=self._snatch_summary_rows,
            output_filepath_prefix=self._output_summary_filepath_prefix,
        )

    def get_output_summary_rows(self) -> List[Tuple[str, ...]]:  # pragma: no cover
        return self._tsv_output_summary_rows
