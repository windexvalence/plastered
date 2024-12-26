import csv
from typing import Any, Dict, List, Optional, Tuple

from config.config_parser import AppConfig
from scraper.lastfm_recs_scraper import LastFMRec

from utils.http_utils import initialize_api_client
from utils.logging_utils import get_custom_logger
from utils.red_utils import RedReleaseType, RedReleaseGroup, RedFormatPreferences
from utils.lastfm_utils import LastFMAlbumInfo
from utils.musicbrainz_utils import MBRelease

_LOGGER = get_custom_logger(__name__)

#TODO: implement search flow of:
# 1. lastfm recs scrape results
# 2. lastfm getinfo api results -> release mbid
# 3. release mbid -> release group mbid and associated metadata
# 4. RED search results sorted / filtered by RedFormatPreference settings

_RED_API_BASE_URL = "https://redacted.sh/ajax.php"
_LAST_FM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"
_MUSICBRAINZ_API_BASE_URL = "http://musicbrainz.org/ws/2/"

_SUMMARY_TSV_HEADER = ["entity_type", "lastfm_entity_url", "red_permalink", "release_mbid"]

class ReleaseSearcher(object):
    def __init__(self, app_config: AppConfig):
        self._output_summary_filepath = app_config.get_cli_option("output_summary_filepath")
        self._use_release_type = app_config.get_cli_option("use_release_type")
        self._use_first_release_year = app_config.get_cli_option("use_first_release_year")
        self._use_record_label = app_config.get_cli_option("use_record_label")
        self._use_catalog_number = app_config.get_cli_option("use_catalog_number")
        self._require_mbid_resolution = (self._use_release_type or self._use_first_release_year or self._use_record_label or self._use_catalog_number)
        self._red_client = initialize_api_client(
            base_api_url=_RED_API_BASE_URL,
            max_api_call_retries=app_config.get_cli_option("red_api_retries"),
            seconds_between_api_calls=app_config.get_cli_option("red_api_seconds_between_calls"),
        )
        self._red_client.headers.update({"Authorization": app_config.get_cli_option("red_api_key")})

        if self._require_mbid_resolution:
            self._last_fm_client = initialize_api_client(
                base_api_url=_LAST_FM_API_BASE_URL,
                max_api_call_retries=app_config.get_cli_option("last_fm_api_retries"),
                seconds_between_api_calls=app_config.get_cli_option("last_fm_api_seconds_between_calls"),
            )
            self._last_fm_api_key = app_config.get_cli_option("last_fm_api_key")
            self._musicbrainz_client = initialize_api_client(
                base_api_url=_MUSICBRAINZ_API_BASE_URL,
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
        self._tsv_output_summary_rows: List[List[str]] = []

    # TODO: add logic for a `search_for_track_rec` that basically ends up just calling this
    def search_for_album_rec(self, last_fm_artist_str: str, last_fm_album_str: str) -> Optional[Tuple[str, Optional[str]]]:
        """
        Searches for the recommended album, and returns a tuple containing the permalink for the best RED match 
        and the release mbid (if an mbid is found / the app is configured to request an mbid from lastfm's API)
        according to format_preferences, search preferences, and snatch preferences.
        Returns None if no viable match is found.
        """
        # If filtering the RED searches by any of these fields, then grab the release mbid from lastfm, then hit musicbrainz to get the relevant data fields.
        release_type, first_release_year, record_label, catalog_number = None, None, None, None
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
            first_release_year=first_release_year if self._use_first_release_year else None,
            record_label=record_label if self._use_record_label else None,
            catalog_number=catalog_number if self._use_catalog_number else None,
        )

        if best_torrent_entry:
            return (best_torrent_entry.get_permalink_url(), release_mbid)
        _LOGGER.warning(f"Could not find any valid search matches for artist: '{last_fm_artist_str}', album: '{last_fm_album_str}'")
        return None
    
    def search_for_album_recs(self, album_recs: List[LastFMRec]) -> List[Optional[str]]:
        """
        Iterate over the list of album_recs and search for each one on RED.
        Returns the list of RED permalinks which match the search criteria for the given LastFMRec.
        Optionally will save the .torrent files in the specified snatch directory.
        """
        for album_rec in album_recs:
            search_result = self.search_for_album_rec(
                last_fm_artist_str=album_rec.artist_str,
                last_fm_album_str=album_rec.entity_str,
            )
            if not search_result:
                continue
            red_permalink, release_mbid = search_result
            cur_tsv_output_row = ["album", album_rec.last_fm_entity_url, red_permalink, str(release_mbid)]
            self._tsv_output_summary_rows.append(cur_tsv_output_row)
            # TODO: optionally write a TSV with the format '{lastfm_entity_url}\t{red_permalink}'
    
    # TODO: optionally download the torrent from permalink
    def snatch_matches(self) -> None:
        pass  # TODO: implement
    
    def write_output_summary_tsv(self) -> None:
        _LOGGER.info(f"Writing search match summary to tsv file at: {self._output_summary_filepath} ...")
        with open(self._output_summary_filepath, "w") as f:
            tsv_writer = csv.writer(f, delimiter='\t', lineterminator='\n')
            tsv_writer.writerow(_SUMMARY_TSV_HEADER)
            for row in self._tsv_output_summary_rows:
                tsv_writer.writerow(row)
