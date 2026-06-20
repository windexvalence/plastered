from typing import Any

import pytest

from plastered.models import LFMAlbumInfo, RedUserDetails


@pytest.fixture(scope="function")
def no_snatch_user_details(mock_red_user_response: dict[str, Any]) -> RedUserDetails:
    return RedUserDetails(
        user_id=12345, snatched_count=0, snatched_torrents_list=[], user_profile_json=mock_red_user_response["response"]
    )


@pytest.fixture(scope="session")
def mock_lfmai() -> LFMAlbumInfo:
    return LFMAlbumInfo(artist="Foo", release_mbid="1234", album_name="Bar", lfm_url="https://blah.com")
