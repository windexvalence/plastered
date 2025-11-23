from typing import Any
from unittest.mock import MagicMock

import pytest

from plastered.db.db_models import Result
from plastered.models.red_models import RedUserDetails
from plastered.models.types import EntityType


@pytest.fixture(scope="function")
def no_snatch_user_details(mock_red_user_response: dict[str, Any]) -> RedUserDetails:
    return RedUserDetails(
        user_id=12345, snatched_count=0, snatched_torrents_list=[], user_profile_json=mock_red_user_response["response"]
    )
