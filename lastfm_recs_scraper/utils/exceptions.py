class AppConfigException(Exception):
    """Exception for invalid configuration errors."""

    pass


class ReleaseSearcherException(Exception):
    """Exception for invalid ReleaseSearcher configurations or execution errors."""

    pass


class RunCacheException(Exception):
    """Exception for invalid RunCache configurations or execution errors."""
    pass
