from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import requests

from lastfm_recs_scraper.utils.constants import STORAGE_UNIT_IDENTIFIERS
from lastfm_recs_scraper.utils.http_utils import request_red_api
from lastfm_recs_scraper.utils.logging_utils import get_custom_logger

_LOGGER = get_custom_logger(__name__)


# File formats
class FormatEnum(Enum):
    FLAC = "FLAC"
    MP3 = "MP3"


# Media
class MediaEnum(Enum):
    ANY = "ANY"  # TODO: update search logic to omit media filters if this is the set value
    CASSETTE = "Cassette"
    CD = "CD"
    SACD = "SACD"
    VINYL = "Vinyl"
    WEB = "WEB"


# Encodings
class EncodingEnum(Enum):
    TWO_FOUR_BIT_LOSSLESS = "24bit+Lossless"
    LOSSLESS = "Lossless"
    MP3_320 = "320"
    MP3_V0 = "V0+(VBR)"


#   "groupId": 1869759,
#   "name": "They Call Me Country",
#   "torrentId": 3928715,
#   "torrentSize": "185876417",
#   "artistName": "Sanford Clark",
#   "artistId": 91298
class PriorSnatch(object):
    def __init__(self, group_id: int, torrent_id: int, red_artist_name: str, red_release_name: str, size: int):
        self._group_id = group_id
        self._torrent_id = torrent_id
        self._red_artist_name = red_artist_name
        self._red_release_name = red_release_name
        self._size = size


# User information (for more refined RED search filtering)
class RedUserDetails(object):
    def __init__(self, user_id: int, snatched_count: int, snatched_torrents_list: List[Dict[str, Any]]):
        self._user_id = user_id
        self._snatched_count = snatched_count
        self._snatched_torrents = snatched_torrents_list
        # mapping from tuple(red artist name, red release name) to PriorSnatch object.
        self._snatched_torrents_dict: Dict[Tuple[str, str], PriorSnatch] = dict()
        for json_entry in self._snatched_torrents:
            red_artist_name = json_entry["artistName"]
            red_release_name = json_entry["name"]
            prior_snatch = PriorSnatch(
                group_id=json_entry["groupId"],
                torrent_id=json_entry["torrentId"],
                red_artist_name=red_artist_name,
                red_release_name=red_release_name,
                size=json_entry["torrentSize"],
            )
            self._snatched_torrents_dict[(red_artist_name.lower(), red_release_name.lower())] = prior_snatch

    def has_snatched_release(self, search_artist: str, search_release: str) -> bool:
        return (search_artist, search_release) in self._snatched_torrents_dict

    def get_user_id(self) -> int:
        return self._user_id

    def get_snatched_count(self) -> int:
        return self._snatched_count


# Defines a singular search preference
class RedFormat:
    def __init__(
        self,
        format: FormatEnum,
        encoding: EncodingEnum,
        media: MediaEnum,
        cd_only_extras: Optional[str] = "",
    ):
        self._format = format
        self._encoding = encoding
        self._media = media
        self._cd_only_extras = cd_only_extras

    def __str__(self) -> str:
        return f"{self._format.value} / {self._encoding.value} / {self._media.value} / {self._cd_only_extras}"

    def __hash__(self) -> int:
        return self.__str__().__hash__()

    def __eq__(self, other) -> bool:
        if not isinstance(other, RedFormat):
            return False
        return (
            self.get_format() == other.get_format()
            and self.get_encoding() == other.get_encoding()
            and self.get_media() == other.get_media()
            and self.get_cd_only_extras() == other.get_cd_only_extras()
        )

    def get_format(self) -> str:
        return self._format.value

    def get_encoding(self) -> str:
        return self._encoding.value

    def get_media(self) -> str:
        return self._media.value

    def get_cd_only_extras(self) -> Optional[str]:
        return self._cd_only_extras if self._cd_only_extras else None


class RedReleaseType(Enum):
    """These enum values are reflective of RED's releaseType API search values."""

    ALBUM = 1
    SOUNDTRACK = 3
    EP = 5
    ANTHOLOGY = 6
    COMPILATION = 7
    SINGLE = 9
    LIVE_ALBUM = 11
    REMIX = 13
    BOOTLEG = 14
    INTERVIEW = 15
    MIXTAPE = 16
    DEMO = 17
    CONCERT_RECORDING = 18
    DJ_MIX = 19
    UNKNOWN = 21


class TorrentEntry(object):
    def __init__(
        self,
        torrent_id: int,
        media: str,
        format: str,
        encoding: str,
        size: float,
        scene: bool,
        trumpable: bool,
        has_snatched: bool,
        has_log: bool,
        log_score: float,
        has_cue: bool,
        reported: Optional[bool] = None,
        lossy_web: Optional[bool] = None,
        lossy_master: Optional[bool] = None,
    ):
        self.torrent_id = torrent_id
        self.media = media
        self.format = format
        self.encoding = encoding
        self.size = size
        self.scene = scene
        self.trumpable = trumpable
        self.has_snatched = has_snatched
        self.has_log = has_log
        self.log_score = log_score
        self.has_cue = has_cue
        self.reported = reported
        self.lossy_web = lossy_web
        self.lossy_master = lossy_master

        cd_only_extras = ""
        if self.media == MediaEnum.CD.value:
            cd_only_extras_list = []
            if self.has_log:
                cd_only_extras_list.append(f"haslog={self.log_score}")
            cd_only_extras_list.append("hascue=1" if self.has_cue else "")
            cd_only_extras = "&".join(cd_only_extras_list)
        self.red_format = RedFormat(
            format=FormatEnum(format),
            encoding=EncodingEnum(encoding.replace(" ", "+")),
            media=MediaEnum(media),
            cd_only_extras=cd_only_extras,
        )

    def __str__(self) -> str:  # pragma: no cover
        return str(vars(self))

    def __eq__(self, other) -> bool:
        if not isinstance(other, TorrentEntry):
            return False
        self_attrs = vars(self)
        other_attrs = vars(other)
        for attr_name, attr_val in self_attrs.items():
            if other_attrs[attr_name] != attr_val:
                return False
        return True

    @classmethod
    def from_torrent_json_blob(cls, json_blob: Dict[str, Any]):
        """
        Construct a TorrentEntry from the JSON data returned from the API endpoint `ajax.php?action=torrent&id<RED-torrent-ID-here>
        """
        return cls(
            torrent_id=json_blob["id"],
            media=json_blob["media"],
            format=json_blob["format"],
            encoding=json_blob["encoding"],
            size=json_blob["size"],
            scene=json_blob["scene"],
            trumpable=json_blob["trumpable"],
            reported=json_blob["reported"],
            lossy_web=json_blob["lossyWebApproved"],
            lossy_master=json_blob["lossyMasterApproved"],
            has_snatched=json_blob["has_snatched"],
            has_log=json_blob["hasLog"],
            log_score=json_blob["logScore"],
            has_cue=json_blob["hasCue"],
        )

    @classmethod
    def from_torrent_search_json_blob(cls, json_blob: Dict[str, Any]):
        """
        Construct a TorrentEntry from the JSON data returned from the `ajax.php?action=browse&<...>` search API endpoint.
        NOTE: TorrentEntry instances constructed via this class method will have their reported, lossy_web, and lossy_master
        fields set to `None`, as the browse endpoint's responses do not surface those pieces of information.
        """
        return cls(
            torrent_id=json_blob["torrentId"],
            media=json_blob["media"],
            format=json_blob["format"],
            encoding=json_blob["encoding"],
            size=json_blob["size"],
            scene=json_blob["scene"],
            trumpable=json_blob["trumpable"],
            has_snatched=json_blob["hasSnatched"],
            has_log=json_blob["hasLog"],
            log_score=json_blob["logScore"],
            has_cue=json_blob["hasCue"],
        )

    def get_size(self, unit: Optional[str] = "B") -> float:
        if unit not in STORAGE_UNIT_IDENTIFIERS:
            raise ValueError(
                f"Unexpected unit_identifier provided: '{unit}'. Must be one of: {STORAGE_UNIT_IDENTIFIERS}"
            )
        if unit == "B":
            return self.size
        elif unit == "MB":
            return float(self.size) / float(1e6)
        return float(self.size) / float(1e9)

    def get_red_format(self) -> RedFormat:
        return self.red_format

    def get_permalink_url(self) -> str:
        return f"https://redacted.sh/torrents.php?torrentid={self.torrent_id}"


class ReleaseEntry(object):
    def __init__(
        self,
        group_id: int,
        media: str,
        remastered: bool,
        remaster_year: int,
        remaster_title: str,
        remaster_catalogue_number: str,
        release_type: RedReleaseType,
        remaster_record_label: Optional[str] = None,
        torrent_entries: Optional[List[TorrentEntry]] = [],
    ):
        self.group_id = group_id
        self.media = media
        self.remastered = remastered
        self.remaster_year = remaster_year
        self.remaster_title = remaster_title
        self.remaster_record_label = remaster_record_label
        self.remaster_catalogue_number = remaster_catalogue_number
        self.release_type = release_type
        self.torrent_entries = torrent_entries

    @classmethod
    def from_torrent_group_json_blob(cls, json_blob: Dict[str, Any], edition_id: int):
        """
        Construct a ReleaseEntry from the JSON data returned from the API endpoint `/ajax.php?action=torrentgroup&id=<group-ID-here>`
        """
        group_json_blob = json_blob["group"]
        group_id = group_json_blob["id"]
        edition_torrents_json = [
            torrent_json for torrent_json in json_blob["torrents"] if torrent_json["editionId"] == edition_id
        ]
        num_torrents_in_edition = len(edition_torrents_json)
        if num_torrents_in_edition == 0:
            raise ValueError(
                f"Invalid edition ID provided for torrent group ID '{group_id}'. No entries found for given edition ID. Unable to construct ReleaseEntry."
            )

        first_torrent_blob = edition_torrents_json[0]
        torrent_entries = [
            TorrentEntry.from_torrent_json_blob(json_blob=torrent_json_blob)
            for torrent_json_blob in edition_torrents_json
        ]

        return cls(
            group_id=group_id,
            media=first_torrent_blob["media"],
            remastered=first_torrent_blob["remastered"],
            remaster_year=first_torrent_blob["remasterYear"],
            remaster_title=first_torrent_blob["remasterTitle"],
            remaster_record_label=first_torrent_blob["remasterRecordLabel"],
            remaster_catalogue_number=first_torrent_blob["remasterCatalogueNumber"],
            release_type=RedReleaseType(group_json_blob["releaseType"]),
            torrent_entries=torrent_entries,
        )

    @classmethod
    def from_torrent_search_json_blob(cls, json_blob: Dict[str, Any]):
        """
        Construct a ReleaseEntry from the JSON data returned from the `ajax.php?action=browse&<...>` search API endpoint.
        NOTE: Instances constructed via this method will have a NoneType `remaster_record_label` value as the `browse` endpoint responses don't surface
        that information.
        """
        first_torrent_blob = json_blob["torrents"][0]
        torrent_entries = [
            TorrentEntry.from_torrent_search_json_blob(json_blob=torrent_json_blob)
            for torrent_json_blob in json_blob["torrents"]
        ]
        return cls(
            group_id=json_blob["groupId"],
            media=first_torrent_blob["media"],
            remastered=first_torrent_blob["remastered"],
            remaster_year=first_torrent_blob["remasterYear"],
            remaster_title=first_torrent_blob["remasterTitle"],
            remaster_catalogue_number=first_torrent_blob["remasterCatalogueNumber"],
            release_type=RedReleaseType[json_blob["releaseType"].upper()],
            torrent_entries=torrent_entries,
        )

    def has_snatched_any(self) -> bool:
        """
        Returns True if any TorrentEntry under this ReleaseEntry has already been snatched, regardless of format.
        Returns False otherwise.
        """
        for te in self.torrent_entries:
            if te.has_snatched:
                _LOGGER.info(f"Found prior snatch in release group id: {self.group_id} for torrent id: {te.torrent_id}")
                return True
        return False

    def get_red_formats(self) -> List[RedFormat]:
        return [torrent_entry.get_red_format() for torrent_entry in self.torrent_entries]

    def get_torrent_entries(self) -> List[TorrentEntry]:
        return self.torrent_entries


class RedReleaseGroup(object):
    def __init__(self, group_id: int, release_entries: Optional[List[ReleaseEntry]] = []):
        self.group_id = group_id
        self.release_entries = release_entries

    @classmethod
    def from_torrent_group_json_blob(cls, json_blob: Dict[str, Any]):
        """
        Construct a RedReleaseGroup from the JSON data returned from the API endpoint `/ajax.php?action=torrentgroup&id=<group-ID-here>`
        """
        group_id = json_blob["group"]["id"]
        torrents_json_list = json_blob["torrents"]
        edition_ids = set([torrent_blob["editionId"] for torrent_blob in torrents_json_list])
        release_entries = [
            ReleaseEntry.from_torrent_group_json_blob(json_blob=json_blob, edition_id=edition_id)
            for edition_id in edition_ids
        ]
        return cls(group_id=group_id, release_entries=release_entries)

    @classmethod
    def from_group_id(cls, group_id: int):
        """
        Construct a RedReleaseGroup instance from the release group ID via the RED torrent group API endpoint.
        """
        torrent_group_json_response = request_red_api(action="torrentgroup", params=f"id={group_id}")
        return RedReleaseGroup.from_torrent_group_json_blob(json_blob=torrent_group_json_response)

    def get_release_group_url(self) -> str:
        return f"https://redacted.sh/torrents.php?id={self.group_id}"


def create_browse_params(
    red_format: RedFormat,
    artist_name: str,
    album_name: str,
    release_type: Optional[RedReleaseType] = None,
    first_release_year: Optional[int] = None,
    record_label: Optional[str] = None,
    catalog_number: Optional[str] = None,
) -> str:
    format = red_format.get_format()
    encoding = red_format.get_encoding()
    media = red_format.get_media()
    # TODO: figure out why the `order_by` param appears to be ignored whenever the params also have `group_results=1`.
    browse_request_params = f"artistname={artist_name}&groupname={album_name}&format={format}&encoding={encoding}&media={media}&group_results=1&order_by=seeders&order_way=desc"
    if release_type:
        browse_request_params += f"&releasetype={release_type.value}"
    if first_release_year:
        browse_request_params += f"&year={first_release_year}"
    if record_label:
        browse_request_params += f"&recordlabel={quote_plus(record_label)}"
    if catalog_number:
        browse_request_params += f"&cataloguenumber={quote_plus(catalog_number)}"
    return browse_request_params


class RedFormatPreferences:
    def __init__(self, preference_ordering: List[RedFormat], max_size_gb: Optional[float] = 5.0):
        self._preference_ordering = preference_ordering
        self._max_size_gb = max_size_gb
        self._format_matches: Dict[RedFormat, List[TorrentEntry]] = {
            red_format: [] for red_format in self._preference_ordering
        }

    # TODO (later): optionally allow for multi-page search
    def search_release_by_preferences(
        self,
        red_client: requests.Session,
        artist_name: str,
        album_name: str,
        release_type: Optional[RedReleaseType] = None,
        first_release_year: Optional[int] = None,
        record_label: Optional[str] = None,
        catalog_number: Optional[str] = None,
    ) -> Optional[TorrentEntry]:
        for pref_red_format in self._preference_ordering:
            browse_request_params = create_browse_params(
                red_format=pref_red_format,
                artist_name=artist_name,
                album_name=album_name,
                release_type=release_type,
                first_release_year=first_release_year,
                record_label=record_label,
                catalog_number=catalog_number,
            )
            red_browse_response = request_red_api(red_client=red_client, action="browse", params=browse_request_params)
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

        return None
