from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict

from plastered.models.types import (
    EncodingEnum,
    FormatEnum,
    GigaBytesValue,
    MediaEnum,
    RedReleaseType,
    coerce_to_float_value,
)
from plastered.utils.constants import BYTES_IN_GB, BYTES_IN_MB, STORAGE_UNIT_IDENTIFIERS


class RedFormat(BaseModel):
    format: FormatEnum
    encoding: EncodingEnum
    media: MediaEnum
    cd_only_extras: str | None = None

    def get_format(self) -> str:
        return self.format.value

    def get_encoding(self) -> str:
        return self.encoding.value

    def get_media(self) -> str:
        return self.media.value

    def get_cd_only_extras(self) -> str | None:
        return self.cd_only_extras
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, RedFormat):
            return False
        return other.format == self.format and other.encoding == self.encoding and other.media == self.media and other.cd_only_extras == self.cd_only_extras


# Media
# Encodings
class PriorSnatch(BaseModel):
    """
    Utility class representing a distinct snatched torrent for a given user.
    Used by the ReleaseSearcher to filter out any pre-snatched recommendations.
    """

    group_id: int
    torrent_id: int
    red_artist_name: str
    red_release_name: str
    size: int


@dataclass
class TorrentEntry:
    """Utility class wrapping the details of a distinct torrent on RED."""

    # pylint: disable=redefined-builtin
    torrent_id: int
    media: str
    format: str
    encoding: str
    size: float
    scene: bool
    trumpable: bool
    has_snatched: bool
    has_log: bool
    log_score: float
    has_cue: bool
    can_use_token: bool
    reported: bool | None = None
    lossy_web: bool | None = None
    lossy_master: bool | None = None
    matched_mbid: str | None = None
    artist_name: str | None = None
    release_name: str | None = None
    track_rec_name: str | None = None
    red_format: RedFormat | None = None

    def __post_init__(self):
        cd_only_extras = ""
        if self.media == MediaEnum.CD.value:
            cd_only_extras_list = []
            if self.has_log:
                cd_only_extras_list.append(f"haslog={self.log_score}")
            cd_only_extras_list.append("hascue=1" if self.has_cue else "")
            cd_only_extras = "&".join(cd_only_extras_list)
        self.red_format = RedFormat(
            format=FormatEnum(self.format),
            encoding=EncodingEnum(self.encoding.replace(" ", "+")),
            media=MediaEnum(self.media),
            cd_only_extras=cd_only_extras,
        )

    # TODO: see if this can be removed
    def __eq__(self, other) -> bool:
        if not isinstance(other, TorrentEntry):
            return False
        self_attrs = vars(self)
        other_attrs = vars(other)
        return all([other_attrs[attr_name] == attr_val for attr_name, attr_val in self_attrs.items()])

    @classmethod
    def from_torrent_search_json_blob(cls, json_blob: dict[str, Any]):
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

    def get_size(self, unit: str | None = "B") -> float:
        if unit not in STORAGE_UNIT_IDENTIFIERS:
            raise ValueError(
                f"Unexpected unit_identifier provided: '{unit}'. Must be one of: {STORAGE_UNIT_IDENTIFIERS}"
            )
        if unit == "B":
            return self.size
        if unit == "MB":
            return float(self.size) / BYTES_IN_MB
        return float(self.size) / BYTES_IN_GB

    def get_permalink_url(self) -> str:
        return f"https://redacted.sh/torrents.php?torrentid={self.torrent_id}"


# TODO (later): reformat this as a dataclass
# Defines a singular search preference
# NOTE: the browse response returns the releaseType string value, rather than the int
def _red_release_type_str_to_enum(release_type_str: str) -> RedReleaseType:
    return RedReleaseType[release_type_str.replace(" ", "_").upper()]


@dataclass
class ReleaseEntry:
    """
    Utility class wrapping the details of a given specific release within a RED release group,
    along with all the individual torrents associated with this specific release.
    """

    group_id: int
    media: str
    remastered: bool
    remaster_year: int
    remaster_title: str
    remaster_catalogue_number: str
    release_type: RedReleaseType
    remaster_record_label: str | None = None
    torrent_entries: list[TorrentEntry] | None = field(default_factory=list)

    @classmethod
    def from_torrent_search_json_blob(cls, json_blob: dict[str, Any]):
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

    def get_red_formats(self) -> list[RedFormat]:
        return [torrent_entry.red_format for torrent_entry in self.torrent_entries]

    def get_torrent_entries(self) -> list[TorrentEntry]:
        return self.torrent_entries


class _RedUserInitialStats(BaseModel):
    model_config = ConfigDict(extra="ignore")
    uploaded: GigaBytesValue
    downloaded: GigaBytesValue
    buffer: GigaBytesValue
    ratio: Annotated[float, BeforeValidator(coerce_to_float_value)]
    initial_available_fl_tokens: int = 0


# User information (for more refined RED search filtering)
class RedUserDetails(BaseModel):
    """
    Utility class representing a distinct RED user.
    Used by the ReleaseSearcher to determine the user's pre-snatched torrents, and filter out any pre-snatched recommendations.
    """
    model_config = ConfigDict(extra="ignore")
    user_id: int
    snatched_count: int
    snatched_torrents_list: list[dict[str, Any]]
    user_profile_json: dict[str, Any]
    _initial_stats: _RedUserInitialStats
    _snatched_tids: set[str]
    _snatched_torrents_dict: dict[tuple[str, str], PriorSnatch]

    def model_post_init(self, context: Any) -> None:
        self._initial_stats = _RedUserInitialStats(
            initial_available_fl_tokens=(
                self.user_profile_json["personal"].get("giftTokens", 0)
                + self.user_profile_json["personal"].get("meritTokens", 0)
            ),
            **self.user_profile_json["stats"],
        )
        self._snatched_tids = set()
        self._snatched_torrents_dict = dict()
        for json_entry in self.snatched_torrents_list:
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

    def get_initial_available_fl_tokens(self) -> int:
        """
        Returns the initial number of FL tokens available at the start of a scrape run.
        Passed to the RedApiClient instance for the client to maintain a relatively accurate accounting of FL tokens
        if FL usage is enabled.
        """
        return self._initial_stats.initial_available_fl_tokens

    def calculate_max_download_allowed_gb(self, min_allowed_ratio: float) -> float:
        """
        Calculates the maximum total GB which can be snatched from RED during the current run.
        Returns the lesser of the two values:
            (a) the user's initial buffer at the start of the run,
            (b) OR the additional DL (in GB) required to bring the user's ratio down to their configured 'min_allowed_ratio' config setting.
        """
        init_stats = self._initial_stats
        if min_allowed_ratio <= 0:
            return self._initial_stats.buffer
        # Solve for constraint init_U / (init_D + max_allowed_run_dl) >= min_allowed_ratio
        ratio_max_allowed_run_dl = init_stats.uploaded / min_allowed_ratio - init_stats.downloaded
        return max(min(ratio_max_allowed_run_dl, init_stats.buffer), 0.0)
