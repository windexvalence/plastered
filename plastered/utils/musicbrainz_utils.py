import re
from typing import Any, Dict, Optional

from plastered.utils.red_utils import RedReleaseType

_RELEASE_YEAR_REGEX_PATTERN = re.compile(r"^([0-9]{4})[^0-9]*.*")


class MBRelease:
    """
    Utility class wrapping the contents of a response from the Musicbrainz 'release' API endpoint.
    Optionally used by the ReleaseSearcher for fine-grained RED browsing / filtering.
    """

    def __init__(
        self,
        mbid: str,
        title: str,
        artist: str,
        primary_type: str,
        release_date: str,
        release_group_mbid: str,
        label: Optional[str] = None,
        catalog_number: Optional[str] = None,
        first_release_year: Optional[int] = -1,
    ):
        self._mbid = mbid
        self._title = title
        self._artist = artist
        self._primary_type = primary_type
        self._first_release_year = first_release_year
        self._release_date = release_date
        self._label = label
        self._catalog_number = catalog_number
        self._release_group_mbid = release_group_mbid

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

    def __eq__(self, other) -> bool:
        if not isinstance(other, MBRelease):
            return False
        self_attrs = vars(self)
        other_attrs = vars(other)
        for attr_name, attr_val in self_attrs.items():
            if other_attrs[attr_name] != attr_val:
                return False
        return True

    def get_red_release_type(self) -> RedReleaseType:
        return RedReleaseType[self._primary_type.upper()]

    def get_first_release_year(self) -> int:
        return self._first_release_year

    def get_label(self) -> Optional[str]:
        return self._label

    def get_catalog_number(self) -> Optional[str]:
        return self._catalog_number

    def get_musicbrainz_release_url(self) -> str:
        return f"https://musicbrainz.org/release/{self._mbid}"

    def get_musicbrainz_release_group_url(self) -> str:
        return f"https://musicbrainz.org/release-group/{self._release_group_mbid}"

    def get_release_searcher_kwargs(self) -> Dict[str, Any]:
        """Helper method to return the search_kwargs used by the ReleaseSearcher."""
        return {
            "release_type": self.get_red_release_type(),
            "first_release_year": self.get_first_release_year(),
            "record_label": self.get_label(),
            "catalog_number": self.get_catalog_number(),
        }
