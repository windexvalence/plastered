from typing import Any, Dict, List, Optional

import pytest

from plastered.config.config_parser import AppConfig
from plastered.release_search.search_helpers import (
    SearchItem,
    SearchState,
    _require_mbid_resolution,
)
from plastered.scraper.lfm_scraper import LFMRec, RecContext, RecommendationType
from plastered.utils.musicbrainz_utils import MBRelease
from plastered.utils.red_utils import (
    EncodingEnum,
    FormatEnum,
    MediaEnum,
    RedFormat,
    RedReleaseType,
)

# from tests.conftest import


# TODO: implement
@pytest.mark.parametrize(
    "red_format, primary_type, first_release_year, record_label, catalog_number, expected_browse_params",
    [
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.WEB),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=WEB&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.MP3, encoding=EncodingEnum.MP3_V0, media=MediaEnum.CD),
            None,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=MP3&encoding=V0+(VBR)&media=CD&group_results=1&order_by=seeders&order_way=desc",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            RedReleaseType.ALBUM,
            None,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&releasetype=1",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            1969,
            None,
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&year=1969",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            None,
            None,
            "Fake Label",
            None,
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&recordlabel=Fake+Label",
        ),
        (
            RedFormat(format=FormatEnum.FLAC, encoding=EncodingEnum.TWO_FOUR_BIT_LOSSLESS, media=MediaEnum.WEB),
            "Album",
            None,
            None,
            "FL 69420",
            f"artistname=Some+Artist&groupname=Some+Bad+Album&format=FLAC&encoding=24bit+Lossless&media=WEB&group_results=1&order_by=seeders&order_way=desc&cataloguenumber=FL+69420",
        ),
    ],
)
def test_create_browse_params(
    valid_app_config: AppConfig,
    red_format: RedFormat,
    primary_type: Optional[str],
    first_release_year: Optional[int],
    record_label: Optional[str],
    catalog_number: Optional[str],
    expected_browse_params: str,
) -> None:
    search_state = SearchState(app_config=valid_app_config)
    search_state._use_release_type = True
    search_state._use_first_release_year = True
    search_state._use_record_label = True
    search_state._use_catalog_number = True
    si = SearchItem(
        _lfm_rec=LFMRec(
            lfm_artist_str="Some+Artist",
            lfm_entity_str="Some+Bad+Album",
            recommendation_type=RecommendationType.ALBUM,
            rec_context=RecContext.SIMILAR_ARTIST,
        )
    )
    mbr = MBRelease(
        mbid="",
        title="",
        artist="",
        primary_type="" if primary_type is None else primary_type,
        release_date="",
        release_group_mbid="",
        label=record_label,
        catalog_number=catalog_number,
        first_release_year=first_release_year,
    )
    si.set_mb_release(mbr=mbr)
    actual_browse_params = search_state.create_red_browse_params(red_format=red_format, si=si)
    assert (
        actual_browse_params == expected_browse_params
    ), f"Expected browse params to be '{expected_browse_params}', but got '{actual_browse_params}' instead."


@pytest.mark.parametrize(
    "use_release_type, use_first_release_year, use_record_label, use_catalog_number, expected",
    [
        (False, False, False, False, False),
        (False, False, False, True, True),
        (False, False, True, False, True),
        (False, True, False, False, True),
        (True, False, False, False, True),
        (True, False, False, True, True),
        (True, False, True, False, True),
        (True, True, False, False, True),
        (True, True, False, True, True),
        (True, True, True, False, True),
        (True, True, True, True, True),
    ],
)
def test_require_mbid_resolution(
    use_release_type: bool,
    use_first_release_year: bool,
    use_record_label: bool,
    use_catalog_number: bool,
    expected: bool,
) -> None:
    actual = _require_mbid_resolution(
        use_release_type=use_release_type,
        use_first_release_year=use_first_release_year,
        use_record_label=use_record_label,
        use_catalog_number=use_catalog_number,
    )
    assert actual == expected, f"Expected {expected}, but got {actual}"
