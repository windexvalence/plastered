import csv
import os
from typing import Any, Dict, List, Optional, Tuple

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm
from urllib.parse import quote_plus, unquote_plus

from lastfm_recs_scraper.config.config_parser import AppConfig
from lastfm_recs_scraper.scraper.lastfm_recs_scraper import LastFMRec
from lastfm_recs_scraper.utils.constants import (
    LAST_FM_API_BASE_URL,
    MUSICBRAINZ_API_BASE_URL,
    RED_API_BASE_URL,
)
from lastfm_recs_scraper.utils.exceptions import ReleaseSearcherException
from lastfm_recs_scraper.utils.http_utils import initialize_api_client, request_red_api
from lastfm_recs_scraper.utils.lastfm_utils import LastFMAlbumInfo
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger
from lastfm_recs_scraper.utils.musicbrainz_utils import MBRelease
from lastfm_recs_scraper.utils.red_utils import (
    RedUserDetails,
    RedFormatPreferences,
    RedReleaseGroup,
    RedReleaseType,
)

_LOGGER = get_custom_logger(__name__)

_SUMMARY_TSV_HEADER = [
    "entity_type",
    "rec_context",
    "lastfm_entity_url",
    "red_permalink",
    "release_mbid",
]


def require_mbid_resolution(
    use_release_type: bool, use_first_release_year: bool, use_record_label: bool, use_catalog_number: bool
) -> bool:
    return use_release_type or use_first_release_year or use_record_label or use_catalog_number


def lastfm_format_to_user_details_format(lastfm_format_str: str) -> str:
    """
    Utility function which takes a lastfm url-encoded string representing an artist or release, and returns 
    the human-readable string. For example "Some+Band" -> "Some Band"
    """
    return unquote_plus(lastfm_format_str.lower())


class ReleaseSearcher(object):
    def __init__(self, app_config: AppConfig):
        self._red_user_id = app_config.get_cli_option("red_user_id")
        self._red_user_details: Optional[RedUserDetails] = None
        self._skip_prior_snatches = app_config.get_cli_option("skip_prior_snatches")
        self._output_summary_filepath = app_config.get_cli_option("output_summary_filepath")
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
        self._red_client = initialize_api_client(
            base_api_url=RED_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("red_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("red_api_seconds_between_calls"),
        )
        self._red_client.headers.update({"Authorization": app_config.get_cli_option("red_api_key")})

        if self._require_mbid_resolution:
            self._last_fm_client = initialize_api_client(
                base_api_url=LAST_FM_API_BASE_URL,
                max_api_call_retries=app_config.get_cli_option("last_fm_api_retries"),
                seconds_between_api_calls=app_config.get_cli_option("last_fm_api_seconds_between_calls"),
            )
            self._last_fm_api_key = app_config.get_cli_option("last_fm_api_key")
            self._musicbrainz_client = initialize_api_client(
                base_api_url=MUSICBRAINZ_API_BASE_URL,
                max_api_call_retries=app_config.get_cli_option("musicbrainz_api_max_retries"),
                seconds_between_api_calls=app_config.get_cli_option("musicbrainz_api_seconds_between_calls"),
            )
        else:
            self._last_fm_client = None
            self._musicbrainz_client = None
        self._red_format_preferences = RedFormatPreferences(
            preference_ordering=app_config.get_red_preference_ordering(),
            max_size_gb=app_config.get_cli_option("max_size_gb"),
        )
        self._tsv_output_summary_rows = []
        self._permalinks_to_snatch = []
    
    def gather_red_user_details(self) -> None:
        _LOGGER.info(f"Gathering red user details to help with search filtering ...")
        user_stats_json = request_red_api(red_client=self._red_client, action="community_stats", params=f"userid={self._red_user_id}")
        snatched_torrent_count = int(user_stats_json["snatched"].replace(",", ""))
        user_torrents_json = request_red_api(red_client=self._red_client, action="user_torrents", params=f"id={self._red_user_id}&type=snatched&limit={snatched_torrent_count}&offset=0")
        self._red_user_details = RedUserDetails(
            user_id=self._red_user_id,
            snatched_count=snatched_torrent_count,
            snatched_torrents_list=user_torrents_json["snatched"],
        )

    # TODO: add logic for a `search_for_track_rec` that basically ends up just calling this
    def search_for_album_rec(
        self, last_fm_artist_str: str, last_fm_album_str: str
    ) -> Optional[Tuple[str, Optional[str]]]:
        """
        Searches for the recommended album, and returns a tuple containing the permalink for the best RED match
        and the release mbid (if an mbid is found / the app is configured to request an mbid from lastfm's API)
        according to format_preferences, search preferences, and snatch preferences.
        Returns None if no viable match is found.
        """
        if self._skip_prior_snatches:
            search_artist_str = lastfm_format_to_user_details_format(lastfm_format_str=last_fm_artist_str)
            search_album_str = lastfm_format_to_user_details_format(lastfm_format_str=last_fm_album_str)
            if self._red_user_details.has_snatched_release(search_artist=search_artist_str, search_release=search_album_str):
                _LOGGER.info(f"Skipping album search for artist: '{search_artist_str}', album: '{search_album_str}' due to pre-existing snatch found in release group. To download from release groups with prior snatches, change the 'skip_prior_snatches' config field.")
                return None
        # If filtering the RED searches by any of these fields, then grab the release mbid from lastfm, then hit musicbrainz to get the relevant data fields.
        release_type, first_release_year, record_label, catalog_number = (
            None,
            None,
            None,
            None,
        )
        release_mbid = None
        if self._require_mbid_resolution:
            lastfm_album_info = LastFMAlbumInfo.construct_from_api_response(
                self._last_fm_client,
                last_fm_api_key=self._last_fm_api_key,
                last_fm_artist_name=last_fm_artist_str,
                last_fm_album_name=last_fm_album_str,
            )
            release_mbid = lastfm_album_info.get_release_mbid()
            mb_release = MBRelease.construct_from_api(musicbrainz_client=self._musicbrainz_client, mbid=release_mbid)
            release_type = mb_release.get_red_release_type()
            first_release_year = mb_release.get_first_release_year()
            record_label = mb_release.get_label()
            catalog_number = mb_release.get_catalog_number()

        best_torrent_entry = self._red_format_preferences.search_release_by_preferences(
            red_client=self._red_client,
            artist_name=last_fm_artist_str,
            album_name=last_fm_album_str,
            release_type=release_type if self._use_release_type else None,
            first_release_year=(first_release_year if self._use_first_release_year else None),
            record_label=record_label if self._use_record_label else None,
            catalog_number=catalog_number if self._use_catalog_number else None,
        )

        if best_torrent_entry:
            return (best_torrent_entry.get_permalink_url(), release_mbid)
        _LOGGER.warning(
            f"Could not find any valid search matches for artist: '{last_fm_artist_str}', album: '{last_fm_album_str}'"
        )
        return None

    def search_for_album_recs(self, album_recs: List[LastFMRec]) -> List[Optional[str]]:
        """
        Iterate over the list of album_recs and search for each one on RED.
        Returns the list of RED permalinks which match the search criteria for the given LastFMRec.
        Optionally will save the .torrent files in the specified snatch directory.
        """
        if self._skip_prior_snatches and self._red_user_details is None:
            raise ReleaseSearcherException(f"self._skip_prior_snatches set to {self._skip_prior_snatches}, but self._red_user_details has not yet been populated.")
        # TODO: make sure this doesnt break logging: https://stackoverflow.com/a/69145493
        with logging_redirect_tqdm(loggers=[_LOGGER]):
            for album_rec in tqdm(album_recs, desc="Searching album recs"):
                search_result = self.search_for_album_rec(
                    last_fm_artist_str=album_rec.artist_str,
                    last_fm_album_str=album_rec.entity_str,
                )
                if not search_result:
                    continue
                red_permalink, release_mbid = search_result
                cur_tsv_output_row = (
                    "album",
                    album_rec.rec_context.value,
                    album_rec.last_fm_entity_url,
                    red_permalink,
                    str(release_mbid),
                )
                self._tsv_output_summary_rows.append(cur_tsv_output_row)
                self._permalinks_to_snatch.append(red_permalink)

    def snatch_matches(self) -> None:
        if not self._enable_snatches:
            _LOGGER.warning(f"Not configured to snatch. Please update your config to enable.")
            return
        _LOGGER.info(f"Beginning to snatch matched permalinks to download directory '{self._snatch_directory}' ...")
        for permalink in self._permalinks_to_snatch:
            tid = permalink.split("=")[-1]
            out_filepath = os.path.join(self._snatch_directory, f"{tid}.torrent")
            _LOGGER.info(f"Snatching {permalink} and saving to {out_filepath} ...")
            binary_contents = request_red_api(red_client=self._red_client, action="download", params=f"id={tid}")
            with open(out_filepath, "wb") as f:
                f.write(binary_contents)

    def get_output_summary_rows(self) -> List[Tuple[str, ...]]:  # pragma: no cover
        return self._tsv_output_summary_rows

    def write_output_summary_tsv(self) -> None:
        _LOGGER.info(f"Writing search match summary to tsv file at: {self._output_summary_filepath} ...")
        with open(self._output_summary_filepath, "w") as f:
            tsv_writer = csv.writer(f, delimiter="\t", lineterminator="\n")
            tsv_writer.writerow(_SUMMARY_TSV_HEADER)
            for row in self.get_output_summary_rows():
                tsv_writer.writerow(row)
