from collections.abc import Callable

import pytest

from plastered.models import MediaEnum, RedReleaseType, ReleaseEntry, TorrentEntry


@pytest.fixture(scope="session")
def make_release_entry() -> Callable:
    """Fixture factory to generate `ReleaseEntry` items on the fly."""

    def _make_release_entry(
        torrent_entries: list[TorrentEntry],
        media: MediaEnum = MediaEnum.CD,
        release_type: RedReleaseType = RedReleaseType.ALBUM,
    ) -> ReleaseEntry:
        return ReleaseEntry(
            group_id=69, media=str(media), release_type=release_type, torrent_entries=torrent_entries, remastered=False
        )

    return _make_release_entry
