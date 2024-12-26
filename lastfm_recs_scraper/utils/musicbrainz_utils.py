import requests
from lastfm_recs_scraper.utils.http_utils import request_musicbrainz_api
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger
from lastfm_recs_scraper.utils.red_utils import RedReleaseType

_LOGGER = get_custom_logger(__name__)


class MBRelease(object):
    def __init__(
        self,
        mbid: str,
        title: str,
        artist: str,
        primary_type: str,
        first_release_year: int,
        release_date: str,
        label: str,
        catalog_number: str,
        release_group_mbid: str,
    ):
        self._mbid = mbid
        self._title = title
        self._artist = artist
        self._primary_type = primary_type
        self._first_release_year = first_release_year
        self._release_date = release_date
        self._label = label
        self._catalog_number = catalog_number
        self._release_group_mbid = release_group_mbid

    @classmethod
    def construct_from_api(cls, musicbrainz_client: requests.Session, mbid: str):
        json_blob = request_musicbrainz_api(
            musicbrainz_client=musicbrainz_client, entity_type="release", mbid=mbid
        )
        label_json = json_blob["label-info"]
        release_group_json = json_blob["release-group"]
        return cls(
            mbid=json_blob["id"],
            title=json_blob["title"],
            artist=json_blob["artist-credit"][0]["name"],
            primary_type=release_group_json["primary-type"],
            first_release_year=release_group_json["first-release-date"],
            release_date=json_blob["date"],
            label=label_json["label"]["name"],
            catalog_number=label_json["catalog-number"],
            release_group_mbid=release_group_json["id"],
        )

    def get_red_release_type(self) -> RedReleaseType:
        return RedReleaseType[self._primary_type.upper()]

    def get_first_release_year(self) -> int:
        return self._first_release_year

    def get_label(self) -> str:
        return self._label

    def get_catalog_number(self) -> str:
        return self._catalog_number

    def get_musicbrainz_release_url(self) -> str:
        return f"https://musicbrainz.org/release/{self._mbid}"

    def get_musicbrainz_release_group_url(self) -> str:
        return f"https://musicbrainz.org/release-group/{self._release_group_mbid}"


# TODO: pull mbid from lastfm API like so:
# curl -H "Accept: application/json" 'http://ws.audioscrobbler.com/2.0/?method=album.getinfo&api_key=69bc2a48d2d2e77fc8d28bf0d3c1abde&artist=Dr.+Octagon&album=Dr.+Octagonecologyst&format=json' > ~/Downloads/doc_oc_lastfm_response.json


# TODO: setup API utilities for MBID lookups
# curl -H "Accept: application/json" 'http://musicbrainz.org/ws/2/release-group/c9fdb94c-4975-4ed6-a96f-ef6d80bb7738?inc=artist-credits+releases'
# https://musicbrainz.org/doc/MusicBrainz_API/Examples#Release_Group
