"""
Models for the ad-hoc ("manual") release search flow.

An ad-hoc search is any release search that does NOT originate from the LFM scraper. It is submitted directly by a
client (the web UI or a REST client) and, unlike an `LFMRec`, is not required to carry any Last.fm-specific data. The
only required fields are the `artist` plus exactly one of `release` (album name) or `track` name. Every other field
(MBID, catalog number, record label, release year, release type) is optional and, when present, is used to refine the
RED browse query.

`AdhocSearch` implements the same read interface that the `ReleaseSearcher` processor chain expects from a search's
`initial_info` (see `plastered.models.search_item.SearchItem`), so the existing album/track processor chains work for
both the scraper flow (`LFMRec`) and the ad-hoc flow without branching.
"""

from collections import OrderedDict
from datetime import datetime
from typing import Any, Self
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field, model_validator

from plastered.models.types import EntityType, RecContext, RedReleaseType
from plastered.utils.constants import (
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
)


def _default_submit_timestamp_factory() -> int:
    return int(datetime.now().timestamp())


class AdhocSearch(BaseModel):
    """
    The non-LFM `initial_info` for a `SearchItem`. Represents a single ad-hoc release search request.

    `release` (album name) and `track` are mutually informative: when a `release` is provided the search is treated as
    an album search keyed on that release; otherwise (only a `track` is provided) it is treated as a track search and
    the originating release is resolved via the LFM / MusicBrainz APIs, exactly as for an LFM track rec.
    """

    model_config = ConfigDict(extra="forbid")
    artist: str = Field(min_length=1)
    release: str | None = Field(default=None)
    track: str | None = Field(default=None)
    mbid: str | None = Field(default=None)
    # Optional fields used to refine the RED browse query when present. They map directly to RED browse params.
    release_type: RedReleaseType | None = Field(default=None)
    release_year: int | None = Field(default=None)
    record_label: str | None = Field(default=None)
    catalog_number: str | None = Field(default=None)
    submit_timestamp: int = Field(default_factory=_default_submit_timestamp_factory)

    @model_validator(mode="after")
    def _require_release_or_track(self) -> Self:
        if not self.release and not self.track:
            raise ValueError("An ad-hoc search requires at least one of 'release' (album name) or 'track'.")
        return self

    @property
    def entity_type(self) -> EntityType:
        """An ad-hoc search with a `release` is an album search; otherwise it is a track search."""
        return EntityType.ALBUM if self.release else EntityType.TRACK

    @property
    def _entity(self) -> str:
        """The human-readable primary entity name (the release for album searches, else the track)."""
        # The model validator guarantees at least one of `release`/`track` is set.
        return self.release if self.release else self.track  # type: ignore[return-value]

    @property
    def encoded_artist_str(self) -> str:
        return quote_plus(self.artist)

    @property
    def encoded_entity_str(self) -> str:
        return quote_plus(self._entity)

    @property
    def lfm_entity_url(self) -> str:
        if self.entity_type == EntityType.ALBUM:
            return f"https://www.last.fm/music/{self.encoded_artist_str}/{self.encoded_entity_str}"
        return f"https://www.last.fm/music/{self.encoded_artist_str}/_/{self.encoded_entity_str}"

    @property
    def rec_context(self) -> RecContext:
        # Ad-hoc searches have no LFM recommendation context.
        return RecContext.NOT_SET

    def get_human_readable_artist_str(self) -> str:
        return self.artist

    def get_human_readable_entity_str(self) -> str:
        return self._entity

    def get_human_readable_track_str(self) -> str:
        if self.entity_type != EntityType.TRACK:
            raise ValueError("Cannot get track name from an album ad-hoc search.")
        return self._entity

    def get_user_search_kwargs(self) -> OrderedDict[str, Any]:
        """
        Returns the user-supplied optional RED browse params (URL-encoded where needed), omitting any unset fields.
        These take precedence over any values later resolved from MusicBrainz (see `SearchItem.set_mb_release`).
        """
        kwargs: OrderedDict[str, Any] = OrderedDict()
        if self.release_type is not None:
            kwargs[RED_PARAM_RELEASE_TYPE] = self.release_type.value
        if self.release_year is not None:
            kwargs[RED_PARAM_RELEASE_YEAR] = self.release_year
        if self.record_label:
            kwargs[RED_PARAM_RECORD_LABEL] = quote_plus(self.record_label)
        if self.catalog_number:
            kwargs[RED_PARAM_CATALOG_NUMBER] = quote_plus(self.catalog_number)
        return kwargs
