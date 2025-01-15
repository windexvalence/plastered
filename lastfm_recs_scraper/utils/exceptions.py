class AppConfigException(Exception):
    """Exception for invalid configuration errors."""

    pass


class ReleaseSearcherException(Exception):
    """Exception for invalid ReleaseSearcher configurations or execution errors."""

    pass


class RedClientSnatchException(Exception):
    """Exception for failed snatch attempts from a RedAPIClient.snatch(...) call."""
    pass


class RunCacheException(Exception):
    """Exception for invalid RunCache configurations or execution errors."""

    pass


class RunCacheDisabledException(Exception):
    """
    Specific Exception raised when enabled-only methods are called on a RunCache instance which is not enabled.
    """
    pass


class StatsTableException(Exception):
    """
    Exception for errors from StatsTable / subclasses.
    """
    pass

