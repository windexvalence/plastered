import re
from enum import Enum, StrEnum
from typing import Any, Dict, List, Optional, Tuple

from plastered.utils.constants import STORAGE_UNIT_IDENTIFIERS

_CD_EXTRAS_PRETTY_PRINT_REGEX_PATTERN = re.compile(r"^haslog=([0-9]+)&hascue=([0-9]+)$")


# File formats
class FormatEnum(StrEnum):
    """Enum class to map to the supported file format search fields on the RED API"""

    FLAC = "FLAC"
    MP3 = "MP3"


# Media
class MediaEnum(StrEnum):
    """Enum class to map to the supported media search fields on the RED API"""

    ANY = "ANY"  # TODO: update search logic to omit media filters if this is the set value
    CASSETTE = "Cassette"
    CD = "CD"
    SACD = "SACD"
    VINYL = "Vinyl"
    WEB = "WEB"


# Encodings
class EncodingEnum(StrEnum):
    """Enum class to map to the supported encoding search fields on the RED API"""

    TWO_FOUR_BIT_LOSSLESS = "24bit+Lossless"
    LOSSLESS = "Lossless"
    MP3_320 = "320"
    MP3_V0 = "V0+(VBR)"


class PriorSnatch:
    """
    Utility class representing a distinct snatched torrent for a given user.
    Used by the ReleaseSearcher to filter out any pre-snatched recommendations.
    """

    def __init__(self, group_id: int, torrent_id: int, red_artist_name: str, red_release_name: str, size: int):
        self._group_id = group_id
        self._torrent_id = torrent_id
        self._red_artist_name = red_artist_name
        self._red_release_name = red_release_name
        self._size = size


# User information (for more refined RED search filtering)
class RedUserDetails:
    """
    Utility class representing a distinct RED user.
    Used by the ReleaseSearcher to determine the user's pre-snatched torrents, and filter out any pre-snatched recommendations.
    """

    def __init__(self, user_id: int, snatched_count: int, snatched_torrents_list: List[Dict[str, Any]]):
        self._user_id = user_id
        self._snatched_count = snatched_count
        self._snatched_torrents = snatched_torrents_list
        self._snatched_tids = set()
        # mapping from tuple(red artist name, red release name) to PriorSnatch object.
        self._snatched_torrents_dict: Dict[Tuple[str, str], PriorSnatch] = dict()
        for json_entry in self._snatched_torrents:
            red_artist_name = json_entry["artistName"]
            red_release_name = json_entry["name"]
            tid = json_entry["torrentId"]
            prior_snatch = PriorSnatch(
                group_id=json_entry["groupId"],
                torrent_id=tid,
                red_artist_name=red_artist_name,
                red_release_name=red_release_name,
                size=json_entry["torrentSize"],
            )
            self._snatched_torrents_dict[(red_artist_name.lower(), red_release_name.lower())] = prior_snatch
            self._snatched_tids.add(tid)

    # This method specifically is for pre-RED search filtering of the LFM recs, since the LFM recs do not yet have a potential TID associated with them.
    def has_snatched_release(self, artist: str, release: str) -> bool:
        """
        Searches whether the release was already listed in the user's snatched torrents.
        NOTE: 'artist' and 'album' must be the human-readable, non URL-encoded strings.
        """
        return (artist.lower(), release.lower()) in self._snatched_torrents_dict

    # This method is for specifically pre-snatch filtering of matched RED releases.
    def has_snatched_tid(self, tid: int) -> bool:
        """
        Returns True if the provided tid is already in the user's snatched / seeding torrents list.
        Returns False otherwise.
        """
        return tid in self._snatched_tids

    def get_user_id(self) -> int:
        return self._user_id

    def get_snatched_count(self) -> int:
        return self._snatched_count


# Defines a singular search preference
class RedFormat:
    """
    Utility class representing a unique entry in the user's preferred torrent qualities.
    Used by the ReleaseSearcher for filtering and/or prioritizing specific desired file qualities.
    """

    # pylint: disable=redefined-builtin
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

    def get_yaml_dict_for_pretty_print(self) -> Dict[str, Any]:
        entries = {"format": self._format.value, "encoding": self._encoding.value, "media": self._encoding.value}
        if self._cd_only_extras:
            log_str, cue_str = _CD_EXTRAS_PRETTY_PRINT_REGEX_PATTERN.findall(self._cd_only_extras)[0]
            entries["cd_only_extras"] = {"log": int(log_str), "has_cue": True if int(cue_str) else False}
        return {"preference": entries}

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
    PRODUCED_BY = 1021
    COMPOSITION = 1022
    REMIXED_BY = 1023
    GUEST_APPEARANCE = 1024


# NOTE: the browse response returns the releaseType string value, rather than the int
def _red_release_type_str_to_enum(release_type_str: str) -> RedReleaseType:
    return RedReleaseType[release_type_str.replace(" ", "_").upper()]


class TorrentEntry:
    """Utility class wrapping the details of a distinct torrent on RED."""

    # pylint: disable=redefined-builtin
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
        can_use_token: bool,
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
        self.can_use_token = can_use_token
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
        self._matched_mbid: Optional[str] = None
        self._lfm_rec_type: Optional[str] = None
        self._lfm_rec_context: Optional[str] = None
        self._artist_name: Optional[str] = None
        self._release_name: Optional[str] = None
        self._track_rec_name: Optional[str] = None

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
            can_use_token=json_blob["canUseToken"],
        )

    def set_matched_mbid(self, matched_mbid: str) -> None:
        self._matched_mbid = matched_mbid

    def set_lfm_rec_fields(
        self, rec_type: str, rec_context: str, artist_name: str, release_name: str, track_rec_name: Optional[str] = None
    ) -> None:
        self._lfm_rec_type = rec_type
        self._lfm_rec_context = rec_context
        self._artist_name = artist_name
        self._release_name = release_name
        self._track_rec_name = track_rec_name

    def get_matched_mbid(self) -> Optional[str]:
        return self._matched_mbid

    def get_lfm_rec_type(self) -> Optional[str]:
        return self._lfm_rec_type

    def get_lfm_rec_context(self) -> Optional[str]:
        return self._lfm_rec_context

    def get_artist_name(self) -> Optional[str]:
        return self._artist_name

    def get_release_name(self) -> Optional[str]:
        return self._release_name

    def get_track_rec_name(self) -> Optional[str]:
        return self._track_rec_name

    def token_usable(self) -> bool:
        return self.can_use_token

    def get_size(self, unit: Optional[str] = "B") -> float:
        if unit not in STORAGE_UNIT_IDENTIFIERS:
            raise ValueError(
                f"Unexpected unit_identifier provided: '{unit}'. Must be one of: {STORAGE_UNIT_IDENTIFIERS}"
            )
        if unit == "B":
            return self.size
        if unit == "MB":
            return float(self.size) / float(1e6)
        return float(self.size) / float(1e9)

    def get_red_format(self) -> RedFormat:
        return self.red_format

    def get_permalink_url(self) -> str:
        return f"https://redacted.sh/torrents.php?torrentid={self.torrent_id}"


class ReleaseEntry:
    """
    Utility class wrapping the details of a given specific release within a RED release group,
    along with all the individual torrents associated with this specific release.
    """

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
            release_type=_red_release_type_str_to_enum(release_type_str=json_blob["releaseType"]),
            torrent_entries=torrent_entries,
        )

    def get_red_formats(self) -> List[RedFormat]:
        return [torrent_entry.get_red_format() for torrent_entry in self.torrent_entries]

    def get_torrent_entries(self) -> List[TorrentEntry]:
        return self.torrent_entries
