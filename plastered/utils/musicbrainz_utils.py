import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import quote_plus

from plastered.utils.red_utils import RedReleaseType

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
    label: Optional[str] = None
    catalog_number: Optional[str] = None
    first_release_year: Optional[int] = -1

    @classmethod
    def construct_from_api(cls, json_blob: Dict[str, Any]):
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
        return RedReleaseType[self.primary_type.upper()]

    def get_first_release_year(self) -> int:
        return self.first_release_year

    def get_label(self) -> Optional[str]:
        return self.label

    def get_catalog_number(self) -> Optional[str]:
        return self.catalog_number

    def get_musicbrainz_release_url(self) -> str:
        return f"https://musicbrainz.org/release/{self.mbid}"

    def get_musicbrainz_release_group_url(self) -> str:
        return f"https://musicbrainz.org/release-group/{self.release_group_mbid}"

    def get_release_searcher_kwargs(self) -> OrderedDict[str, Any]:
        """Helper method to return the search_kwargs used by the ReleaseSearcher on the RED browse endpoint."""
        return OrderedDict(
            [
                ("releasetype", self.get_red_release_type().value),
                (
                    "year",
                    (
                        self.first_release_year
                        if (self.first_release_year is not None and self.first_release_year > 0)
                        else None
                    ),
                ),
                ("recordlabel", quote_plus(self.label) if self.label else None),
                ("cataloguenumber", quote_plus(self.catalog_number) if self.catalog_number else None),
            ]
        )
