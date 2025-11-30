from typing import Any


class AppConfigException(Exception):
    """Exception for invalid configuration errors."""

    pass


class ScraperException(Exception):
    """Exception for scraper errors."""

    pass


class LFMRecException(Exception):
    """Exception for invalid LFMRec instance configuration / execution errors."""

    pass


class ReleaseSearcherException(Exception):
    """Exception for invalid ReleaseSearcher configurations or execution errors."""

    pass


class SearchStateException(Exception):
    """Exception for bad or malformed SearchState instances."""

    pass


class SearchItemException(Exception):
    """Exception for malformed or bad SearchItem instances."""

    pass


class MissingTorrentEntryException(SearchItemException):
    """Exception for SearchItem instances which do not have a torrent entry set when they should."""

    pass


class MissingDatabaseRecordException(SearchItemException):
    """Exception raised when actions performed on SearchItem instances require a corresponding `SearchRecord` record in the DB, but none exists."""

    def __init__(self, initial_info: Any):  # pragma: no cover
        super().__init__(
            f"Expected 'SearchRecord' record is None for SearchItem created from initial info: {str(initial_info)}"
        )


class RedClientSnatchException(Exception):
    """Exception for failed snatch attempts from a RedAPIClient.snatch(...) call."""

    pass


class RedUserDetailsInitError(Exception):
    """Exception for failed attempts to initialize the `RedUserDetails` instance."""

    def __init__(self, failed_step: str):  # pragma: no cover
        super().__init__(f"Failed to get or process user {failed_step} info during RedUserDetails initialization.")


class LFMClientException(Exception):
    """Exception for failed request attempts to the LFM API."""

    pass


class MusicBrainzClientException(Exception):
    """Exception for failed request attempts to the Musicbrainz API."""

    pass


class RunCacheException(Exception):
    """Exception for invalid RunCache configurations or execution errors."""

    pass


class RunCacheDisabledException(RunCacheException):
    """
    Specific Exception raised when enabled-only methods are called on a RunCache instance which is not enabled.
    """

    pass


class StatsTableException(Exception):
    """
    Exception for errors from StatsTable / subclasses.
    """

    pass


class StatsRunPickerException(Exception):
    """
    Exception specifically for the StatsRunPicker errors.
    """

    pass


class PriorRunStatsException(StatsTableException):
    """
    Exception for errors from PriorRunStats instances.
    """

    pass
