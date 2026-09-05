from typing import Any

import pytest

from plastered.models.origin_release import (
    OriginRelease,
    OriginSource,
    artist_credit_matches,
    origin_releases_from_recording,
    rank_origin_candidates,
)
from plastered.models.types import RedReleaseType

_OCTAGON_ARTIST_MBID = "3eba5e02-780b-4acd-befb-d23a0c6708dd"


def _mb(
    title: str,
    primary_type: str | None = "Album",
    secondary_types: tuple[str, ...] = (),
    status: str | None = "Official",
    release_date: str | None = "2000",
    first_release_date: str | None = None,
    release_group_mbid: str | None = None,
    release_mbid: str | None = None,
    source: OriginSource = OriginSource.MB_RECORDING_LOOKUP,
) -> OriginRelease:
    return OriginRelease(
        release_name=title,
        source=source,
        release_mbid=release_mbid,
        release_group_mbid=release_group_mbid,
        primary_type=primary_type,
        secondary_types=secondary_types,
        status=status,
        release_date=release_date,
        first_release_date=first_release_date,
    )


class TestOriginRelease:
    def test_from_lfm_track_info(self, mock_full_lfm_track_info_json: dict[str, Any]) -> None:
        actual = OriginRelease.from_lfm_track_info(json_blob=mock_full_lfm_track_info_json["track"])
        assert actual == OriginRelease(
            release_name="Dr. Octagonecologyst",
            source=OriginSource.LFM,
            release_mbid="cddbf21f-9cd8-4665-a015-3cdc50cdcc72",
        )

    @pytest.mark.parametrize(
        "json_blob", [{}, {"album": "not-a-dict"}, {"album": {}}, {"album": {"title": ""}}], ids=str
    )
    def test_from_lfm_track_info_without_album(self, json_blob: dict[str, Any]) -> None:
        assert OriginRelease.from_lfm_track_info(json_blob=json_blob) is None

    def test_from_lfm_track_info_empty_mbid_is_none(self) -> None:
        actual = OriginRelease.from_lfm_track_info(json_blob={"album": {"title": "X", "mbid": ""}})
        assert actual == OriginRelease(release_name="X", source=OriginSource.LFM, release_mbid=None)

    def test_from_mb_release_json(self, mock_musicbrainz_recording_lookup_json: dict[str, Any]) -> None:
        release_json = mock_musicbrainz_recording_lookup_json["releases"][0]
        actual = OriginRelease.from_mb_release_json(release_json=release_json, source=OriginSource.MB_RECORDING_SEARCH)
        assert actual == OriginRelease(
            release_name="Dr. Octagonecologyst",
            source=OriginSource.MB_RECORDING_SEARCH,
            release_mbid="d211379d-3203-47ed-a0c5-e564815bb45a",
            release_group_mbid="b38e21f6-8f76-3f87-a021-e91afad9e7e5",
            primary_type="Album",
            secondary_types=(),
            status="Official",
            release_date="2017-05-19",
            first_release_date="1996-05-07",
        )

    def test_from_mb_release_json_minimal(self) -> None:
        actual = OriginRelease.from_mb_release_json(
            release_json={"title": "X", "release-group": None}, source=OriginSource.MB_RECORDING_LOOKUP
        )
        assert actual == OriginRelease(release_name="X", source=OriginSource.MB_RECORDING_LOOKUP)

    @pytest.mark.parametrize("release_json", [{}, {"title": ""}, {"id": "abc"}], ids=str)
    def test_from_mb_release_json_without_title(self, release_json: dict[str, Any]) -> None:
        assert OriginRelease.from_mb_release_json(release_json=release_json, source=OriginSource.LFM) is None

    @pytest.mark.parametrize(
        "first_release_date, release_date, expected",
        [
            ("1996-05-07", "2017-05-19", 1996),
            (None, "2017-05-19", 2017),
            (None, "2017", 2017),
            (None, None, None),
            (None, "n/a", None),
        ],
    )
    def test_release_year(self, first_release_date: str | None, release_date: str | None, expected: int | None) -> None:
        origin = _mb("X", release_date=release_date, first_release_date=first_release_date)
        assert origin.release_year == expected

    @pytest.mark.parametrize(
        "primary_type, secondary_types, expected",
        [
            ("Album", (), RedReleaseType.ALBUM),
            ("EP", (), RedReleaseType.EP),
            ("Single", (), RedReleaseType.SINGLE),
            ("Broadcast", (), None),
            (None, (), None),
            # RED files compilations / live albums / soundtracks / remixes under their own types.
            ("Album", ("Compilation",), RedReleaseType.COMPILATION),
            ("Album", ("Live",), RedReleaseType.LIVE_ALBUM),
            ("Album", ("Soundtrack",), RedReleaseType.SOUNDTRACK),
            ("Single", ("Remix",), RedReleaseType.REMIX),
            ("Album", ("DJ-mix",), RedReleaseType.DJ_MIX),
            ("Album", ("Mixtape/Street",), RedReleaseType.MIXTAPE),
            ("Album", ("Demo",), RedReleaseType.DEMO),
            ("Album", ("Interview",), RedReleaseType.INTERVIEW),
            ("Album", ("Audiobook",), RedReleaseType.ALBUM),  # an unmapped secondary type falls back to the primary
            (None, ("Audiobook",), None),
        ],
    )
    def test_get_red_release_type(
        self, primary_type: str | None, secondary_types: tuple[str, ...], expected: RedReleaseType | None
    ) -> None:
        assert _mb("X", primary_type=primary_type, secondary_types=secondary_types).get_red_release_type() == expected

    @pytest.mark.parametrize(
        "primary_type, secondary_types, expected",
        [
            ("Album", (), True),
            ("EP", (), True),
            ("Single", (), True),
            ("Album", ("Soundtrack",), True),
            ("Single", ("Soundtrack",), True),
            ("Album", ("Audiobook",), True),  # an unmapped secondary type: RED files it under the primary type
            # Unknown types pass; the RED-side type restriction still applies to their matches.
            ("Broadcast", (), True),
            (None, (), True),
            ("Album", ("Compilation",), False),
            ("Album", ("Live",), False),
            ("Album", ("Soundtrack", "Compilation"), False),  # any excluded secondary type rules the group out
            ("Single", ("Remix",), False),
            ("Album", ("DJ-mix",), False),
            ("Album", ("Mixtape/Street",), False),
            ("Album", ("Demo",), False),
            ("Album", ("Interview",), False),
        ],
    )
    def test_is_track_origin_type(
        self, primary_type: str | None, secondary_types: tuple[str, ...], expected: bool
    ) -> None:
        assert _mb("X", primary_type=primary_type, secondary_types=secondary_types).is_track_origin_type is expected

    def test_dedupe_key(self) -> None:
        assert _mb("X", release_group_mbid="rg-1").dedupe_key == "rg-1"
        assert _mb("Some Album!").dedupe_key == "title:some album"

    def test_rank_key_ordering(self) -> None:
        """Official albums (earliest first, undated last), then EPs, singles, soundtracks, then everything else."""
        album_2000 = _mb("album 2000", release_date="2000")
        album_2000_reissue = _mb("album 2000 reissue", release_date="2010", first_release_date="2000")
        album_2005 = _mb("album 2005", release_date="2005")
        album_undated = _mb("album undated", release_date=None)
        album_unknown_status = _mb("album unknown status", status=None, release_date="1990")
        ep = _mb("ep", primary_type="EP", release_date="1990")
        single = _mb("single", primary_type="Single", release_date="1990")
        soundtrack = _mb("soundtrack", secondary_types=("Soundtrack",), release_date="1990")
        compilation = _mb("compilation", secondary_types=("Compilation",), release_date="1990")
        promo = _mb("promo", status="Promotion", release_date="1990")
        untyped = _mb("untyped", primary_type=None, release_date="1990")
        candidates = [
            untyped,
            promo,
            compilation,
            soundtrack,
            single,
            ep,
            album_undated,
            album_2005,
            album_2000_reissue,
            album_2000,
            album_unknown_status,
        ]
        actual = sorted(candidates, key=OriginRelease.rank_key)
        assert [c.release_name for c in actual] == [
            "album unknown status",
            "album 2000",
            "album 2000 reissue",
            "album 2005",
            "album undated",
            "ep",
            "single",
            "soundtrack",
            "untyped",
            "promo",
            "compilation",
        ]


_OCTAGON_CREDIT = [
    {
        "name": "Dr. Octagon",
        "joinphrase": "",
        "artist": {"id": _OCTAGON_ARTIST_MBID, "name": "Dr. Octagon", "sort-name": "Octagon, Dr."},
    }
]
_DUO_CREDIT = [
    {"name": "Foo", "joinphrase": " & ", "artist": {"id": "a1", "name": "Foo", "sort-name": "Foo"}},
    {"name": "Bar", "joinphrase": "", "artist": {"id": "a2", "name": "Bar", "sort-name": "Bar"}},
]


@pytest.mark.parametrize(
    "artist_credit_json, artist_name, artist_mbid, expected",
    [
        (_OCTAGON_CREDIT, "Someone Else", _OCTAGON_ARTIST_MBID, True),  # the MBID wins over a name mismatch
        (_OCTAGON_CREDIT, "dr octagon", None, True),  # normalized credit name
        (_OCTAGON_CREDIT, "Octagon, Dr.", None, True),  # sort-name
        ([{"name": "The Credited Alias", "artist": {"id": "x", "name": "Real Name"}}], "Real Name", None, True),
        (_DUO_CREDIT, "Foo and Bar", None, True),  # the credit as a whole
        (_DUO_CREDIT, "Bar", None, True),  # one credited artist of several
        (_OCTAGON_CREDIT, "Someone Else", "other-mbid", False),
        ([], "Dr. Octagon", None, False),
        (None, "Dr. Octagon", None, False),
    ],
)
def test_artist_credit_matches(
    artist_credit_json: list[dict[str, Any]] | None, artist_name: str, artist_mbid: str | None, expected: bool
) -> None:
    assert artist_credit_matches(artist_credit_json, artist_name=artist_name, artist_mbid=artist_mbid) is expected


class TestOriginReleasesFromRecording:
    def test_all_releases_of_a_matching_recording(self, mock_musicbrainz_recording_lookup_json: dict[str, Any]) -> None:
        actual = origin_releases_from_recording(
            recording_json=mock_musicbrainz_recording_lookup_json,
            source=OriginSource.MB_RECORDING_LOOKUP,
            artist_name="Dr. Octagon",
        )
        expected_mbids = [r["id"] for r in mock_musicbrainz_recording_lookup_json["releases"]]
        assert [c.release_mbid for c in actual] == expected_mbids
        assert {c.source for c in actual} == {OriginSource.MB_RECORDING_LOOKUP}

    def test_artist_credit_mismatch_yields_nothing(
        self, mock_musicbrainz_recording_lookup_json: dict[str, Any]
    ) -> None:
        actual = origin_releases_from_recording(
            recording_json=mock_musicbrainz_recording_lookup_json,
            source=OriginSource.MB_RECORDING_LOOKUP,
            artist_name="Someone Else",
        )
        assert actual == []

    @pytest.mark.parametrize(
        "track_name, expected_count",
        [
            ("no awareness", 4),
            ("No Awareness!", 4),
            # LFM track names often carry featured-artist / remaster suffixes MB recording titles omit.
            ("No Awareness (feat. Someone)", 4),
            ("No Awareness - Remastered 2009", 4),
            ("Blue Flowers", 0),
        ],
    )
    def test_track_name_check(
        self, mock_musicbrainz_recording_lookup_json: dict[str, Any], track_name: str, expected_count: int
    ) -> None:
        actual = origin_releases_from_recording(
            recording_json=mock_musicbrainz_recording_lookup_json,
            source=OriginSource.MB_RECORDING_SEARCH,
            artist_name="Dr. Octagon",
            track_name=track_name,
        )
        assert len(actual) == expected_count

    def test_untitled_recording_never_matches_a_track_name(self) -> None:
        recording_json = {"artist-credit": _OCTAGON_CREDIT, "releases": [{"id": "r", "title": "R"}]}
        actual = origin_releases_from_recording(
            recording_json=recording_json,
            source=OriginSource.MB_RECORDING_SEARCH,
            artist_name="Dr. Octagon",
            track_name="X",
        )
        assert actual == []

    def test_suffixed_recording_title_matches_plain_track_name(self) -> None:
        """The reverse of the LFM-suffix case: MB's "Song (live)" recording for a wanted "Song"."""
        recording_json = {
            "title": "No Awareness (live)",
            "artist-credit": _OCTAGON_CREDIT,
            "releases": [{"id": "r", "title": "Live!"}],
        }
        actual = origin_releases_from_recording(
            recording_json=recording_json,
            source=OriginSource.MB_RECORDING_SEARCH,
            artist_name="Dr. Octagon",
            track_name="No Awareness",
        )
        assert [c.release_name for c in actual] == ["Live!"]

    def test_untitled_releases_are_skipped(self) -> None:
        recording_json = {
            "title": "T",
            "artist-credit": _OCTAGON_CREDIT,
            "releases": [{"id": "no-title"}, {"id": "ok", "title": "OK"}],
        }
        actual = origin_releases_from_recording(
            recording_json=recording_json, source=OriginSource.MB_RECORDING_SEARCH, artist_name="Dr. Octagon"
        )
        assert [c.release_mbid for c in actual] == ["ok"]


class TestRankOriginCandidates:
    def test_orders_by_tier_dedupes_by_release_group_and_drops_non_origin_types(self) -> None:
        reissue = _mb(
            "Album",
            release_date="2010",
            first_release_date="2000",
            release_group_mbid="rg-album",
            release_mbid="reissue",
        )
        original = _mb(
            "Album",
            release_date="2000",
            first_release_date="2000",
            release_group_mbid="rg-album",
            release_mbid="original",
        )
        single = _mb("Single", primary_type="Single", release_date="2000", release_group_mbid="rg-single")
        compilation = _mb("Hits", secondary_types=("Compilation",), release_date="1999", release_group_mbid="rg-hits")
        live = _mb("Live", secondary_types=("Live",), release_date="1999", release_group_mbid="rg-live")
        soundtrack = _mb("OST", secondary_types=("Soundtrack",), release_date="1999", release_group_mbid="rg-ost")
        ep = _mb("EP", primary_type="EP", release_date="2001", release_group_mbid="rg-ep")
        actual = rank_origin_candidates(mb_candidates=[compilation, soundtrack, single, live, reissue, ep, original])
        assert [c.release_mbid or c.release_name for c in actual] == ["original", "EP", "Single", "OST"]

    @pytest.mark.parametrize("lfm_mbid, lfm_title", [("m1", "Other Title"), ("other-mbid", "Greatest Hits!")])
    def test_lfm_candidate_folded_into_a_dropped_candidate_is_dropped_too(self, lfm_mbid: str, lfm_title: str) -> None:
        """MB knowing the LFM album (by MBID or title) as a compilation rules it out as an origin release."""
        hits = _mb("Greatest Hits", secondary_types=("Compilation",), release_group_mbid="rg", release_mbid="m1")
        lfm = OriginRelease(release_name=lfm_title, source=OriginSource.LFM, release_mbid=lfm_mbid)
        assert rank_origin_candidates(mb_candidates=[hits], lfm_candidate=lfm) == []

    def test_lfm_candidate_folded_by_release_mbid(self) -> None:
        mb_album = _mb("Album (Deluxe)", release_group_mbid="rg", release_mbid="m1")
        lfm = OriginRelease(release_name="Album", source=OriginSource.LFM, release_mbid="m1")
        assert rank_origin_candidates(mb_candidates=[mb_album], lfm_candidate=lfm) == [mb_album]

    def test_lfm_candidate_folded_by_title(self) -> None:
        mb_album = _mb("Some Album", release_group_mbid="rg", release_mbid="m1")
        lfm = OriginRelease(release_name="Some Album!", source=OriginSource.LFM, release_mbid="other")
        assert rank_origin_candidates(mb_candidates=[mb_album], lfm_candidate=lfm) == [mb_album]

    def test_unique_lfm_candidate_ranks_last(self) -> None:
        single = _mb("Single", primary_type="Single", release_group_mbid="rg")
        lfm = OriginRelease(release_name="Greatest Hits", source=OriginSource.LFM)
        assert rank_origin_candidates(mb_candidates=[single], lfm_candidate=lfm) == [single, lfm]

    def test_lfm_candidate_alone(self) -> None:
        lfm = OriginRelease(release_name="Album", source=OriginSource.LFM)
        assert rank_origin_candidates(mb_candidates=[], lfm_candidate=lfm) == [lfm]

    def test_nothing(self) -> None:
        assert rank_origin_candidates(mb_candidates=[], lfm_candidate=None) == []
