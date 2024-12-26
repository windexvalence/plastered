from enum import Enum
from typing import Any, Dict, List, Optional

import requests
from urllib.parse import quote_plus

from utils.http_utils import request_red_api
from utils.logging_utils import get_custom_logger


_LOGGER = get_custom_logger(__name__)


# File formats
class FormatEnum(Enum):
    FLAC = "FLAC"
    MP3 = "MP3"

# Media
class MediaEnum(Enum):
    ANY = "ANY" # TODO: update search logic to omit media filters if this is the set value
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

# Defines a singular search preference
class RedFormat:
    def __init__(self, format: FormatEnum, encoding: EncodingEnum, media: MediaEnum, cd_only_extras: Optional[str] = ""):
        self._format = format
        self._encoding = encoding
        self._media = media
        self._cd_only_extras = cd_only_extras
    
    def __str__(self) -> str:
        return f"{self._format.value} / {self._encoding.value} / {self._media.value} / {self._cd_only_extras}"
    
    def __hash__(self) -> int:
        return self.__str__().__hash__()
    
    def get_format(self) -> str:
        return self._format.value

    def get_encoding(self) -> str:
        return self._encoding.value

    def get_media(self) -> str:
        return self._media.value

    def get_cd_only_extras(self) -> Optional[str]:
        return self._cd_only_extras if self._cd_only_extras else None

_UNIT_IDENTIFIERS = ["B", "MB", "GB"]

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
        reported: Optional[bool],
        lossy_web: Optional[bool],
        lossy_master: Optional[bool],
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
            if self.has_log:
                cd_only_extras += f"haslog={self.log_score}"
            cd_only_extras += "hascue=1" if self.has_cue else ""
        self.red_format = RedFormat(
            format=FormatEnum(format),
            encoding=EncodingEnum(quote_plus(encoding)),
            media=MediaEnum(media),
            cd_only_extras=cd_only_extras,
        )
    
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
        if unit not in _UNIT_IDENTIFIERS:
            raise ValueError(f"Unexpected unit_identifier provided: '{unit}'. Must be one of: {_UNIT_IDENTIFIERS}")
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
        remaster_record_label: Optional[str],
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
        edition_torrents_json = [torrent_json for torrent_json in json_blob["torrents"] if torrent_json["editionId"] == edition_id]
        num_torrents_in_edition = len(edition_torrents_json)
        if num_torrents_in_edition == 0:
            raise ValueError(f"Invalid edition ID provided for torrent group ID '{group_id}'. No entries found for given edition ID. Unable to construct ReleaseEntry.")
        
        first_torrent_blob = edition_torrents_json[0]
        torrent_entries = [TorrentEntry.from_torrent_json_blob(json_blob=torrent_json_blob) for torrent_json_blob in edition_torrents_json]

        return cls(
            group_id = group_id,
            media = first_torrent_blob["media"],
            remastered = first_torrent_blob["remastered"],
            remaster_year = first_torrent_blob["remasterYear"],
            remaster_title = first_torrent_blob["remasterTitle"],
            remaster_record_label = first_torrent_blob["remasterRecordLabel"],
            remaster_catalogue_number = first_torrent_blob["remasterCatalogueNumber"],
            release_type = RedReleaseType(group_json_blob["releaseType"]),
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
        torrent_entries = [TorrentEntry.from_torrent_search_json_blob(json_blob=torrent_json_blob) for torrent_json_blob in json_blob["torrents"]]
        return cls(
            group_id=json_blob["groupId"],
            media=first_torrent_blob["media"],
            remastered=first_torrent_blob["remastered"],
            remaster_year=first_torrent_blob["remasterYear"],
            remaster_title=first_torrent_blob["remasterTitle"],
            remaster_catalogue_number=first_torrent_blob["remasterCatalogueNumber"],
            release_type=RedReleaseType(json_blob["releaseType"]),
            torrent_entries=torrent_entries,
        )
    
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
        release_entries = [ReleaseEntry.from_torrent_group_json_blob(json_blob=json_blob, edition_id=edition_id) for edition_id in edition_ids]
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


class RedFormatPreferences:
    def  __init__(self, preference_ordering: List[RedFormat], max_size_gb: Optional[float] = 5.0):
        self._preference_ordering = preference_ordering
        self._max_size_gb = max_size_gb
        self._format_matches: Dict[RedFormat, List[TorrentEntry]] = {
            red_format: [] for red_format in self._preference_ordering
        }
    
    def search_release_by_preferences(
        self,
        red_client: requests.Session,
        artist_name: str,
        album_name: str,
        release_type: Optional[RedReleaseType],
        first_release_year: Optional[int],
        record_label: Optional[str],
        catalog_number: Optional[str],
    ) -> Optional[TorrentEntry]:
        found = False
        for pref in self._preference_ordering:
            format = pref.get_format()
            encoding = pref.get_encoding()
            media = pref.get_media()
            browse_request_params = f"artistname={artist_name}&groupname={album_name}&format={format}&encoding={encoding}&media={media}&order_by=seeders&order_way=desc"
            if release_type:
                browse_request_params += f"&eleasetype={release_type.value}"
            if first_release_year:
                browse_request_params += f"&year={first_release_year}"
            if record_label:
                browse_request_params += f"&recordlabel={quote_plus(record_label)}"
            if catalog_number:
                browse_request_params += f"&cataloguenumber={quote_plus(catalog_number)}"
            red_browse_response = request_red_api(red_client=red_client, action="browse", params=browse_request_params)
            if len(red_browse_response["results"]) > 0:
                for result_blob in red_browse_response["results"]:
                    release_entry = ReleaseEntry.from_torrent_search_json_blob(result_blob)
                    for torrent_entry in release_entry.get_torrent_entries():
                        size_gb = torrent_entry.get_size(unit="GB")
                        if size_gb <= self._max_size_gb:
                            return torrent_entry
        
        return None
    
    def is_preference_match(self, torrent_entry: TorrentEntry) -> bool:
        """
        Returns True if the provided torrent_entry matches with any of the formats in 
        the specified preference_ordering. Returns False otherwise.
        """
        candidate_size_gb = torrent_entry.get_size(unit="GB")
        if candidate_size_gb > self._max_size_gb:
            _LOGGER.warning(f"Torrent entry larger than specified max size: '{candidate_size_gb}' > '{self._max_size_gb}'")
            return False
        return torrent_entry.get_red_format() in self._format_matches
    
    def add_preference_match(self, torrent_entry: TorrentEntry) -> None:
        """Record a match for a given format in the specified preference_ordering."""
        candidate_format = torrent_entry.get_red_format()
        if candidate_format not in self._format_matches:
            raise ValueError(f"candidate torrent_entry does not match any of the provided format preferences.")
        self._format_matches[candidate_format].append(torrent_entry)
    
    def get_preference_matches(self) -> Dict[RedFormat, List[TorrentEntry]]:
        return self._format_matches
