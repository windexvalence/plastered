from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from plastered.models.adhoc_search_models import AdhocSearch
from plastered.models.lfm_models import LFMAlbumInfo, LFMRec, LFMTrackInfo
from plastered.models.musicbrainz_models import MBRelease
from plastered.models.red_models import TorrentEntry, TorrentMatch
from plastered.models.types import EntityType

type InitialInfo = LFMRec | AdhocSearch


# TODO [later]: Consolidate the `SearchRecord` db model and `SearchItem` into a single class.
@dataclass
class SearchItem:
    """
    Class which represents the full range of possible information that may be associated with an LFMRec over the
    duration of a search run. Ultimately, this is the individual object which most of the search functionality will work with
    and/or update during the search and filtering resolution of a given rec.
    """

    initial_info: InitialInfo
    release_name: str = field(init=False)
    above_max_size_te_found: bool | None = False
    torrent_entry: TorrentEntry | None = None
    search_id: int | None = None
    _lfm_album_info: LFMAlbumInfo | None = None
    _lfm_track_info: LFMTrackInfo | None = None
    _mb_release: MBRelease | None = None
    _search_kwargs: OrderedDict[str, Any] = field(default_factory=OrderedDict)

    def __post_init__(self):
        """
        Set the initial `release_name` value based on the instance's other attributes.
        Note: The `release_name` value may change later on for a Track rec, depending on
        LFMTi resolution (see `ReleaseSearcher._resolve__resolve_lfm_track_info` and `SearchItem.set_lfm_track_info`).
        For more on dataclasses and __post_init__ method, see this SO answer: https://stackoverflow.com/a/76187691
        """
        if self.initial_info.entity_type == EntityType.ALBUM.value:
            self.release_name = self.initial_info.get_human_readable_entity_str()
        else:
            self.release_name = "None" if not self._lfm_track_info else self._lfm_track_info.release_name
        # Ad-hoc searches may carry user-supplied optional RED browse params; seed them up-front so they are used even
        # when no MBID resolution takes place (and so they take precedence over any MB-resolved values).
        if isinstance(self.initial_info, AdhocSearch):
            self._search_kwargs = self.initial_info.get_user_search_kwargs()

    @property
    def artist_name(self) -> str:
        """Returns the human-readable artist name."""
        return self.initial_info.get_human_readable_artist_str()

    @property
    def track_name(self) -> str:
        """Returns the human-readable track name."""
        return self.initial_info.get_human_readable_track_str()

    @property
    def is_manual(self) -> bool:
        """Returns `True` if the SearchItem is an ad-hoc (non-scraper) search, otherwise `False` for an LFMRec."""
        return isinstance(self.initial_info, AdhocSearch)

    def get_search_kwargs(self) -> OrderedDict[str, Any]:
        return self._search_kwargs

    def search_kwargs_has_all_required_fields(self, required_kwargs: set[str]) -> bool:
        """
        Return `True` if all the specified fields are set to non-empty values.
        Return `False` otherwise.
        """
        if not required_kwargs.issubset(set(self._search_kwargs.keys())):
            return False
        return all([self._search_kwargs[k] is not None for k in required_kwargs])

    def get_matched_mbid(self) -> str | None:
        # An ad-hoc search may directly supply the release MBID; prefer it, otherwise fall through to any MBID resolved
        # from the LFM album/track info (the latter applies to ad-hoc track searches, which still resolve a release).
        if isinstance(self.initial_info, AdhocSearch) and self.initial_info.mbid is not None:
            return self.initial_info.mbid
        if self.initial_info.entity_type == EntityType.ALBUM and self._lfm_album_info is not None:
            return self._lfm_album_info.release_mbid
        elif self.initial_info.entity_type == EntityType.TRACK and self._lfm_track_info is not None:
            return self._lfm_track_info.release_mbid
        return None

    def found_red_match(self) -> bool:
        return self.torrent_entry is not None and not self.above_max_size_te_found

    def set_torrent_match_fields(self, torrent_match: TorrentMatch) -> None:
        self.torrent_entry = torrent_match.torrent_entry
        self.above_max_size_te_found = torrent_match.above_max_size_found

    def set_lfm_album_info(self, lfmai: LFMAlbumInfo | None) -> None:
        self._lfm_album_info = lfmai

    def set_lfm_track_info(self, lfmti: LFMTrackInfo | None) -> None:
        self._lfm_track_info = lfmti
        if lfmti:
            self.release_name = lfmti.release_name

    def set_mb_release(self, mbr: MBRelease) -> None:
        self._mb_release = mbr
        # MB-resolved params provide the baseline; any user-supplied (ad-hoc) params already on the item win on conflict.
        merged = mbr.get_release_searcher_kwargs()
        merged.update({k: v for k, v in self._search_kwargs.items() if v is not None})
        self._search_kwargs = merged
