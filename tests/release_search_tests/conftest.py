from typing import Any, Dict

import pytest

from plastered.utils.red_utils import RedUserDetails


@pytest.fixture(scope="function")
def no_snatch_user_details(mock_red_user_response: Dict[str, Any]) -> RedUserDetails:
    return RedUserDetails(
        user_id=12345, snatched_count=0, snatched_torrents_list=[], user_profile_json=mock_red_user_response["response"]
    )
