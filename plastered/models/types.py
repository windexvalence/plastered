from enum import IntEnum, StrEnum
from typing import Annotated, Final

from pydantic import BeforeValidator

from plastered.utils.constants import BYTES_IN_GB


class RedReleaseType(IntEnum):
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


class EncodingEnum(StrEnum):
    """Enum class to map to the supported encoding search fields on the RED API"""

    TWO_FOUR_BIT_LOSSLESS = "24bit+Lossless"
    LOSSLESS = "Lossless"
    MP3_320 = "320"
    MP3_V0 = "V0+(VBR)"


class MediaEnum(StrEnum):
    """Enum class to map to the supported media search fields on the RED API"""

    ANY = "ANY"  # TODO: update search logic to omit media filters if this is the set value
    CASSETTE = "Cassette"
    CD = "CD"
    SACD = "SACD"
    VINYL = "Vinyl"
    WEB = "WEB"


# File formats
class FormatEnum(StrEnum):
    """Enum class to map to the supported file format search fields on the RED API"""

    FLAC = "FLAC"
    MP3 = "MP3"


def coerce_to_float_value(raw_value: str | int) -> float:
    if isinstance(raw_value, str):
        raw_value = int(raw_value)
    return float(raw_value)


def coerce_to_gb_value(bytes_value: str | int) -> float:
    if isinstance(bytes_value, str):
        bytes_value = int(bytes_value)
    if bytes_value < 0:
        raise ValueError("Invalid bytes value. Cannot be negative.")
    return float(bytes_value) / BYTES_IN_GB


GigaBytesValue = Annotated[float, BeforeValidator(coerce_to_gb_value)]


class EntityType(StrEnum):
    """Enum representing the type of entity the search relates to (album or track)."""

    ALBUM = "album"
    TRACK = "track"


ALL_ENTITY_TYPES: Final[tuple[str]] = (et.value for et in EntityType)


class RecContext(StrEnum):
    """
    Enum representing the recommendation's context, as stated by LFM's recommendation page.
    Can be either "in-library", or "similar-artist".

    "in-library" means that the recommendation is for a release from an artist which is already in your library, according to LFM.
    "similar-artist" means that the recommendation is for a release from an artist which is similar to other artists you frequently listen to, according to LFM.
    """

    IN_LIBRARY = "in-library"
    SIMILAR_ARTIST = "similar-artist"
    NOT_SET = "not-set"  # For manual runs only, where the concept of a "rec" isn't relevant
