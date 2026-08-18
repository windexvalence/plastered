import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from plastered.models.types import RedReleaseType
from plastered.utils.constants import (
    RED_PARAM_CATALOG_NUMBER,
    RED_PARAM_RECORD_LABEL,
    RED_PARAM_RELEASE_TYPE,
    RED_PARAM_RELEASE_YEAR,
)

_RELEASE_YEAR_REGEX_PATTERN = re.compile(r"^([0-9]{4})[^0-9]*.*")


@dataclass
class MBRelease:
    """
    Utility class wrapping the contents of a response from the Musicbrainz 'release' API endpoint.
    Optionally used by the ReleaseSearcher for fine-grained RED browsing / filtering.
    """

    mbid: str
    title: str
    artist: str
    primary_type: str
    release_date: str
    release_group_mbid: str
    label: str | None = None
    catalog_number: str | None = None
    first_release_year: int = -1

    @classmethod
    def construct_from_api(cls, json_blob: dict[str, Any]):
        label_json = None if not json_blob["label-info"] else json_blob["label-info"][0]
        release_group_json = json_blob["release-group"]
        first_release_year = -1
        if "first-release-date" in release_group_json:
            first_release_year_match = _RELEASE_YEAR_REGEX_PATTERN.match(release_group_json["first-release-date"])
            if first_release_year_match:
                first_release_year = int(first_release_year_match.groups()[0])
        return cls(
            mbid=json_blob["id"],
            title=json_blob["title"],
            artist=json_blob["artist-credit"][0]["name"],
            primary_type=release_group_json["primary-type"],
            first_release_year=first_release_year,
            release_group_mbid=release_group_json["id"],
            release_date=json_blob["date"],
            label=None if not label_json else label_json["label"]["name"],
            catalog_number=None if not label_json else label_json["catalog-number"],
        )

    def get_red_release_type(self) -> RedReleaseType:
        # MusicBrainz may return a null primary-type, or a value RED has no enum for (e.g. "Broadcast", "Other").
        # Fall back to UNKNOWN rather than raising AttributeError/KeyError, which would otherwise abort the search run.
        if not self.primary_type:
            return RedReleaseType.UNKNOWN
        try:
            return RedReleaseType[self.primary_type.upper()]
        except KeyError:
            return RedReleaseType.UNKNOWN

    def get_release_searcher_kwargs(self) -> OrderedDict[str, Any]:
        """
        Helper method to return the search_kwargs used by the ReleaseSearcher when matching RED release groups
        client-side (see `SearchState.get_candidate_release_groups`). Values are the raw (non URL-encoded) strings.
        """
        red_release_type = self.get_red_release_type()
        return OrderedDict(
            [
                # An UNKNOWN release type (a null or RED-unmapped MB primary-type) is unusable as a candidate
                # filter — real RED groups essentially never carry it — so report it as unresolved instead. A user
                # who explicitly picks "Unknown" in the ad-hoc form still filters on it (see
                # `AdhocSearch.get_user_search_kwargs`).
                (
                    RED_PARAM_RELEASE_TYPE,
                    red_release_type.value if red_release_type != RedReleaseType.UNKNOWN else None,
                ),
                (
                    RED_PARAM_RELEASE_YEAR,
                    (
                        self.first_release_year
                        if (self.first_release_year is not None and self.first_release_year > 0)
                        else None
                    ),
                ),
                (RED_PARAM_RECORD_LABEL, self.label if self.label else None),
                (RED_PARAM_CATALOG_NUMBER, self.catalog_number if self.catalog_number else None),
            ]
        )
