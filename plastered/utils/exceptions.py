class AppConfigException(Exception):
    """Exception for invalid configuration errors."""

    pass


class LFMRecException(Exception):
    """Exception for invalid LFMRec instance configuration / execution errors."""

    pass


class ReleaseSearcherException(Exception):
    """Exception for invalid ReleaseSearcher configurations or execution errors."""

    pass


class RedClientSnatchException(Exception):
    """Exception for failed snatch attempts from a RedAPIClient.snatch(...) call."""

    pass


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
