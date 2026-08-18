import logging
from dataclasses import dataclass, field
from functools import cached_property
from html import unescape
from typing import Annotated, Any, NamedTuple, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from plastered.models.field_validators import validate_cd_extras_log_value
from plastered.models.types import (
    EncodingEnum,
    FormatEnum,
    GigaBytesValue,
    MediaEnum,
    RedReleaseType,
    coerce_to_float_value,
)
from plastered.utils.constants import BYTES_IN_GB, BYTES_IN_MB, STORAGE_UNIT_IDENTIFIERS

_LOGGER = logging.getLogger(__name__)


class CdOnlyExtras(BaseModel):
    """RED settings defined for a `red.format_preferences.cd_only_extras` entry in the plasterd yaml config."""

    model_config = ConfigDict(title="cd_only_extras")
    log: int
    has_cue: bool

    # model_config = ConfigDict(validate_default=True)
    model_config = ConfigDict(frozen=True, validate_default=True, extra="ignore")

    @model_validator(mode="after")
    def post_model_validator(self) -> CdOnlyExtras:
        validate_cd_extras_log_value(self.log)
        return self


def _red_format_field_title_generator(field_name: str, field_info: Any) -> str:  # pragma: no cover
    """
    Title generator for the JSONSchema titles for fields of `RedFormat`.
    https://docs.pydantic.dev/latest/concepts/json_schema/#using-field_title_generator
    """
    if field_name.endswith("Enum"):
        return field_name.removesuffix("Enum").lower()
    elif field_name == "CdOnlyExtras":
        return "cd_only_extras"
    return field_name


class RedFormat(BaseModel):
    model_config = ConfigDict(field_title_generator=_red_format_field_title_generator)
    format: FormatEnum = Field(title="format")
    encoding: EncodingEnum = Field(title="encoding")
    media: MediaEnum = Field(title="media")
    # TODO: figure out how to override this field's title in JSON schema
    cd_only_extras: CdOnlyExtras | None = None

    @field_validator("format", mode="before")
    @classmethod
    def _coerce_format_str_to_enum(cls, raw_value: str) -> FormatEnum:
        return FormatEnum(raw_value) if isinstance(raw_value, str) else raw_value

    @field_validator("encoding", mode="before")
    @classmethod
    def _coerce_encoding_str_to_enum(cls, raw_value: str) -> EncodingEnum:
        return EncodingEnum(raw_value) if isinstance(raw_value, str) else raw_value

    @field_validator("media", mode="before")
    @classmethod
    def _coerce_media_str_to_enum(cls, raw_value: str) -> MediaEnum:
        return MediaEnum(raw_value) if isinstance(raw_value, str) else raw_value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, RedFormat):
            return False
        return (
            other.format == self.format
            and other.encoding == self.encoding
            and other.media == self.media
            and other.cd_only_extras == self.cd_only_extras
        )


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
    log_score: int
    has_cue: bool
    can_use_token: bool
    seeders: int | None = None
    reported: bool | None = None
    lossy_web: bool | None = None
    lossy_master: bool | None = None
    matched_mbid: str | None = None
    artist_name: str | None = None
    release_name: str | None = None
    track_rec_name: str | None = None
    red_format: RedFormat | None = None

    def __post_init__(self):
        cd_only_extras = None
        if self.media == MediaEnum.CD.value:
            cd_only_extras = CdOnlyExtras(log=self.log_score if self.has_log else -1, has_cue=self.has_cue)
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
    def from_artist_torrent_json_blob(cls, json_blob: dict[str, Any]):
        """
        Construct a TorrentEntry from a torrent object of the `ajax.php?action=artist&<...>` API endpoint's response.
        NOTE: instances constructed via this class method have their reported, lossy_web, and lossy_master fields set
        to `None`, as the artist endpoint's responses do not surface those pieces of information. `trumpable`,
        `hasSnatched`, and `canUseToken` are not documented for every Gazelle variant of the endpoint, so absent keys
        default to conservative values (in particular `can_use_token=False`, so an FL token is never spent on a
        torrent we can't confirm allows it).
        """
        return cls(
            torrent_id=json_blob["id"],
            media=json_blob["media"],
            format=json_blob["format"],
            encoding=json_blob["encoding"],
            size=json_blob["size"],
            scene=json_blob["scene"],
            trumpable=json_blob.get("trumpable", False),
            has_snatched=json_blob.get("hasSnatched", False),
            has_log=json_blob["hasLog"],
            log_score=json_blob["logScore"],
            has_cue=json_blob["hasCue"],
            can_use_token=json_blob.get("canUseToken", False),
            seeders=json_blob.get("seeders"),
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


class TorrentMatch(NamedTuple):
    torrent_entry: TorrentEntry | None
    above_max_size_found: bool


@dataclass
class ReleaseEntry:
    """
    Utility class wrapping a single RED release group — along with all the individual torrents in it — as returned by
    the `ajax.php?action=artist&<...>` API endpoint. Carries the group-level fields used for the client-side
    title/year/release-type matching and record-label/catalogue-number ranking of candidate groups
    (see `SearchState.get_candidate_release_groups`).
    """

    group_id: int
    group_name: str
    release_type: RedReleaseType
    group_year: int | None = None
    # Every record label / catalogue number attached to the group: the group-level (original release) values plus any
    # per-torrent remaster values. Used as ranking signals only — never to drop a group.
    record_labels: frozenset[str] = frozenset()
    catalogue_numbers: frozenset[str] = frozenset()
    torrent_entries: list[TorrentEntry] = field(default_factory=list)

    @classmethod
    def from_artist_torrent_group_json_blob(cls, json_blob: dict[str, Any]):
        """
        Construct a ReleaseEntry from a `torrentgroup` object of the `ajax.php?action=artist&<...>` API endpoint's
        response. Torrents whose format/encoding/media fall outside the supported search enums (e.g. AAC or DSD) can
        never match a configured format preference, so they are skipped rather than failing the whole group.
        """
        torrent_blobs = json_blob.get("torrent", [])
        torrent_entries = []
        for torrent_blob in torrent_blobs:
            try:
                torrent_entries.append(TorrentEntry.from_artist_torrent_json_blob(json_blob=torrent_blob))
            except ValueError:
                _LOGGER.debug(
                    f"Skipping torrent id={torrent_blob.get('id')} in group id={json_blob.get('groupId')}: "
                    "unsupported format/encoding/media."
                )
        # Order the group's torrents best-seeded-first: `select_best_torrent` takes the first size-acceptable torrent
        # per format preference, so this keeps the snatch preferring healthy torrents (the artist endpoint lists
        # torrents in edition order, unlike the seeder-ordered browse results this flow replaced).
        torrent_entries.sort(key=lambda te: te.seeders or 0, reverse=True)
        try:
            release_type = RedReleaseType(json_blob["releaseType"])
        except ValueError:
            # RED may introduce release-type ids the enum doesn't know about; degrade rather than fail the group.
            release_type = RedReleaseType.UNKNOWN
        record_labels = {json_blob.get("groupRecordLabel"), *(tb.get("remasterRecordLabel") for tb in torrent_blobs)}
        catalogue_numbers = {
            json_blob.get("groupCatalogueNumber"),
            *(tb.get("remasterCatalogueNumber") for tb in torrent_blobs),
        }
        return cls(
            group_id=json_blob["groupId"],
            # Text fields in the artist endpoint's response are HTML-escaped (e.g. "&amp;"); unescape them so the
            # client-side title matching and label/catalogue-number ranking compare against the real values.
            group_name=unescape(json_blob["groupName"]),
            release_type=release_type,
            group_year=json_blob.get("groupYear"),
            record_labels=frozenset(unescape(label) for label in record_labels if label),
            catalogue_numbers=frozenset(
                unescape(catalogue_number) for catalogue_number in catalogue_numbers if catalogue_number
            ),
            torrent_entries=torrent_entries,
        )

    def get_torrent_entries(self) -> list[TorrentEntry]:
        return self.torrent_entries


class _RedUserInitialStats(BaseModel):
    model_config = ConfigDict(extra="ignore")
    uploaded: GigaBytesValue
    downloaded: GigaBytesValue
    buffer: GigaBytesValue
    ratio: Annotated[float, BeforeValidator(coerce_to_float_value)]


# User information (for more refined RED search filtering)
class RedUserDetails(BaseModel):
    """
    Utility class representing a distinct RED user.
    Used by the ReleaseSearcher to determine the user's pre-snatched torrents, and filter out any pre-snatched recommendations.
    """

    model_config = ConfigDict(extra="ignore")
    user_id: int
    snatched_count: int
    # TODO: create a model class for snatched torrents.
    snatched_torrents_list: list[dict[str, Any]]
    user_profile_json: dict[str, Any]
    available_fl_tokens: int = Field(default=0)

    @model_validator(mode="after")
    def set_available_fl_tokens(self) -> Self:
        gift_tokens = self.user_profile_json["personal"].get("giftTokens", 0)
        merit_tokens = self.user_profile_json["personal"].get("meritTokens", 0)
        self.available_fl_tokens = gift_tokens + merit_tokens
        return self

    @cached_property
    def _initial_stats(self) -> _RedUserInitialStats:
        return _RedUserInitialStats(**self.user_profile_json["stats"])

    @cached_property
    def _snatched_torrents_dict(self) -> dict[tuple[str, str], PriorSnatch]:
        snatched_dict: dict[tuple[str, str], PriorSnatch] = dict()
        for json_entry in self.snatched_torrents_list:
            red_artist_name = json_entry["artistName"]
            red_release_name = json_entry["name"]
            prior_snatch = PriorSnatch(
                group_id=int(json_entry["groupId"]),
                torrent_id=int(json_entry["torrentId"]),
                red_artist_name=red_artist_name,
                red_release_name=red_release_name,
                size=int(json_entry["torrentSize"]),
            )
            snatched_dict[(red_artist_name.lower(), red_release_name.lower())] = prior_snatch
            # self._snatched_torrents_dict[(red_artist_name.lower(), red_release_name.lower())] = prior_snatch
        return snatched_dict

    @cached_property
    def _snatched_tids(self) -> set[int]:
        return set([int(json_entry["torrentId"]) for json_entry in self.snatched_torrents_list])

    @property
    def has_fl_tokens(self) -> bool:
        return self.available_fl_tokens > 0

    def decrement_fl_tokens(self) -> None:
        self.available_fl_tokens -= 1
        _LOGGER.info(f"Used an FL token. Approximate remaining tokens: {self.available_fl_tokens}")

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

    def calculate_max_download_allowed_gb(self, min_allowed_ratio: float) -> float:
        """
        Calculates the maximum total GB which can be snatched from RED during the current run: the additional DL
        (in GB) required to bring the user's ratio down to their configured 'min_allowed_ratio' config setting,
        capped by the user's initial buffer at the start of the run. A non-positive `min_allowed_ratio` (the
        config default) disables the limit entirely: the run's cumulative download is unbounded.
        """
        init_stats = self._initial_stats
        if min_allowed_ratio <= 0:
            return float("inf")
        # Solve for constraint init_U / (init_D + max_allowed_run_dl) >= min_allowed_ratio
        ratio_max_allowed_run_dl = init_stats.uploaded / min_allowed_ratio - init_stats.downloaded
        return max(min(ratio_max_allowed_run_dl, init_stats.buffer), 0.0)
