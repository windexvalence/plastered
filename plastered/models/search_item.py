from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from plastered.models.lfm_models import LFMAlbumInfo, LFMRec, LFMTrackInfo
from plastered.models.musicbrainz_models import MBRelease
from plastered.models.red_models import TorrentEntry
from plastered.models.types import RecommendationType
from plastered.stats.stats import SkippedReason, SnatchFailureReason
from plastered.utils.constants import STATS_TRACK_REC_NONE


# TODO [later]: Define a separate `MatchedSearchItem` class for matched entries in RED where the te values are guaranteed non-None.
@dataclass
class SearchItem:
    """
    Class which represents the full range of possible information that may be associated with an LFMRec over the
    duration of a search run. Ultimately, this is the individual object which most of the search functionality will work with
    and/or update during the search and filtering resolution of a given rec.
    """

    lfm_rec: LFMRec
    release_name: str = field(init=False)
    above_max_size_te_found: bool | None = False
    torrent_entry: TorrentEntry | None = None
    lfm_album_info: LFMAlbumInfo | None = None
    lfm_track_info: LFMTrackInfo | None = None
    mb_release: MBRelease | None = None
    skip_reason: SkippedReason | None = None
    snatch_failure_reason: SnatchFailureReason | None = None
    search_kwargs: OrderedDict[str, Any] = field(default_factory=OrderedDict)

    def __post_init__(self):
        """
        Set the initial `release_name` value based on the instance's other attributes.
        Note: The `release_name` value may change later on for a Track rec, depending on
        LFMTi resolution (see `ReleaseSearcher._resolve__resolve_lfm_track_info` and `SearchItem.set_lfm_track_info`).
        For more on dataclasses and __post_init__ method, see this SO answer: https://stackoverflow.com/a/76187691
        """
        if self.lfm_rec.rec_type == RecommendationType.ALBUM.value:
            self.release_name = self.lfm_rec.get_human_readable_release_str()
        else:
            self.release_name = "None" if not self.lfm_track_info else self.lfm_track_info.release_name

    @property
    def artist_name(self) -> str:
        """Returns the human-readable artist name."""
        return self.lfm_rec.get_human_readable_artist_str()

    @property
    def track_name(self) -> str:
        """Returns the human-readable track name."""
        return self.lfm_rec.get_human_readable_track_str()

    def get_search_kwargs(self) -> OrderedDict[str, Any]:
        return self.search_kwargs

    def search_kwargs_has_all_required_fields(self, required_kwargs: set[str]) -> bool:
        """
        Return `True` if all the specified fields are set to non-empty values.
        Return `False` otherwise.
        """
        if not required_kwargs.issubset(set(self.search_kwargs.keys())):
            return False
        return all([self.search_kwargs[k] is not None for k in required_kwargs])

    @property
    def track_rec_name(self) -> str | None:
        return (
            STATS_TRACK_REC_NONE
            if self.lfm_rec.rec_type == RecommendationType.ALBUM.value
            else self.lfm_rec.get_human_readable_track_str()
        )

    def get_matched_mbid(self) -> str | None:
        if self.lfm_rec.rec_type == RecommendationType.ALBUM:
            return None if not self.lfm_album_info else self.lfm_album_info.get_release_mbid()
        return None if not self.lfm_track_info else self.lfm_track_info.get_release_mbid()

    def found_red_match(self) -> bool:
        return self.torrent_entry is not None and not self.above_max_size_te_found

    def set_torrent_match_fields(self, torrent_match) -> None:
        self.torrent_entry = torrent_match.torrent_entry
        self.above_max_size_te_found = torrent_match.above_max_size_found

    def set_lfm_album_info(self, lfmai: LFMAlbumInfo | None) -> None:
        self.lfm_album_info = lfmai

    def set_lfm_track_info(self, lfmti: LFMTrackInfo | None) -> None:
        self.lfm_track_info = lfmti
        if lfmti:
            self.release_name = lfmti.release_name

    def set_mb_release(self, mbr: MBRelease) -> None:
        self.mb_release = mbr
        self.search_kwargs = mbr.get_release_searcher_kwargs()
