from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from yt_research.cache import ChannelCache
from yt_research.models import (
    AnalysisQuery,
    Channel,
    ChannelCandidate,
    SortOrder,
    UploadItem,
    Video,
    VideoQuery,
)
from yt_research.research import Research


class FakeYouTubeAPI:
    def __init__(self, channel: Channel, videos: list[Video]) -> None:
        self.channel_value = channel
        self.video_values = videos
        self.resolved: list[str] = []
        self.requested_playlists: list[str] = []
        self.requested_batches: list[list[str]] = []
        self.scanned: list[str] = []
        self._requests: Counter[str] = Counter()

    @property
    def request_counts(self) -> dict[str, int]:
        return dict(self._requests)

    def resolve_channel(self, reference: str) -> Channel:
        self.resolved.append(reference)
        self._requests["channels"] += 1
        return self.channel_value

    def search_channels(self, query: str, limit: int = 10) -> list[ChannelCandidate]:
        self._requests["search"] += 1
        return [
            ChannelCandidate(
                channel_id=self.channel_value.channel_id,
                title=f"{query} Result",
                handle=self.channel_value.handle,
                url=self.channel_value.url,
            )
        ][:limit]

    def iter_uploads(self, playlist_id: str) -> Iterator[UploadItem]:
        self.requested_playlists.append(playlist_id)
        newest_first = sorted(self.video_values, key=lambda item: item.published_at, reverse=True)
        for index, video in enumerate(newest_first):
            if index % 50 == 0:
                self._requests["playlistItems"] += 1
            self.scanned.append(video.video_id)
            yield UploadItem(
                video_id=video.video_id,
                title=video.title,
                published_at=video.published_at,
            )

    def get_videos(self, video_ids: list[str]) -> list[Video]:
        self.requested_batches.append(video_ids)
        self._requests["videos"] += 1
        requested = set(video_ids)
        return [video for video in self.video_values if video.video_id in requested]


def test_channel_report_includes_request_delta(synthetic_channel: Channel) -> None:
    api = FakeYouTubeAPI(synthetic_channel, [])

    report = Research(api).channel("@exampleobservatory")

    assert report.channel == synthetic_channel
    assert report.meta.requests == {"channels": 1}
    assert report.query == {"reference": "@exampleobservatory", "refresh": False}


def test_cached_alias_resolves_stable_id_and_refresh_uses_original_reference(
    tmp_path: Path, synthetic_channel: Channel
) -> None:
    cache = ChannelCache(tmp_path / "cache.sqlite3")
    cache.put("@exampleobservatory", synthetic_channel)
    api = FakeYouTubeAPI(synthetic_channel, [])
    research = Research(api, cache)

    research.channel("@exampleobservatory")
    research.channel("@exampleobservatory", refresh=True)

    assert api.resolved == [synthetic_channel.channel_id, "@exampleobservatory"]


def test_search_returns_candidates_without_resolving(synthetic_channel: Channel) -> None:
    api = FakeYouTubeAPI(synthetic_channel, [])

    candidates = Research(api).search_channels("Fictional Astronomy")

    assert candidates[0].title == "Fictional Astronomy Result"
    assert api.resolved == []


def test_video_filters_are_unicode_case_insensitive_and_use_utc_dates(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    api = FakeYouTubeAPI(synthetic_channel, synthetic_videos)
    query = VideoQuery(match="CAF\u00c9", year=2025)

    report = Research(api).videos("@exampleobservatory", query)

    assert [video.video_id for video in report.items] == ["video-a"]
    assert report.meta.matched == 1
    assert report.meta.returned == 1


def test_video_date_boundaries_are_inclusive(synthetic_channel: Channel) -> None:
    videos = [
        Video(
            video_id=f"video-{day}",
            title="Boundary test",
            url=f"https://www.youtube.com/watch?v=video-{day}",
            published_at=datetime(2025, 1, day, 23, 59, tzinfo=UTC),
            views=day,
        )
        for day in (1, 2, 3)
    ]
    query = VideoQuery.model_validate({"from": "2025-01-01", "to": "2025-01-02"})

    report = Research(FakeYouTubeAPI(synthetic_channel, videos)).videos(
        "@exampleobservatory", query
    )

    assert {video.video_id for video in report.items} == {"video-1", "video-2"}


def test_all_sort_orders_and_limit(synthetic_channel: Channel) -> None:
    videos = [
        Video(
            video_id=f"video-{index}",
            title=f"Video {index}",
            url=f"https://www.youtube.com/watch?v=video-{index}",
            published_at=datetime(2025, index, 1, tzinfo=UTC),
            views=views,
            likes=likes,
        )
        for index, views, likes in [(1, 30, None), (2, 10, 50), (3, 20, 5)]
    ]
    research = Research(FakeYouTubeAPI(synthetic_channel, videos))

    ascending = research.videos(
        synthetic_channel.channel_id,
        VideoQuery(sort=SortOrder.PUBLISHED_ASC),
    )
    top = research.videos(
        synthetic_channel.channel_id,
        VideoQuery(sort=SortOrder.VIEWS, limit=2),
        command="videos.top",
    )
    liked = research.videos(
        synthetic_channel.channel_id,
        VideoQuery(sort=SortOrder.LIKES),
    )

    assert [video.video_id for video in ascending.items] == ["video-1", "video-2", "video-3"]
    assert [video.video_id for video in top.items] == ["video-1", "video-3"]
    assert top.command == "videos.top"
    assert top.meta.truncated is True
    assert [video.video_id for video in liked.items] == ["video-2", "video-3", "video-1"]


def catalog(count: int) -> list[Video]:
    return [
        Video(
            video_id=f"video-{index:04d}",
            title=f"Episode {index}",
            url=f"https://www.youtube.com/watch?v=video-{index:04d}",
            published_at=datetime(2026, 1, 1, tzinfo=UTC) - timedelta(days=index),
            views=index,
        )
        for index in range(count)
    ]


def test_playlist_metadata_filters_uploads_before_they_are_hydrated(
    synthetic_channel: Channel,
) -> None:
    videos = catalog(400)
    api = FakeYouTubeAPI(synthetic_channel, videos)

    report = Research(api).videos(synthetic_channel.channel_id, VideoQuery(year=2026))

    assert [video.video_id for video in report.items] == ["video-0000"]
    assert api.requested_batches == [["video-0000"]]
    assert report.meta.scanned_all is False
    assert len(api.scanned) == 101


def test_newest_first_limit_stops_scanning_after_the_out_of_order_window(
    synthetic_channel: Channel,
) -> None:
    api = FakeYouTubeAPI(synthetic_channel, catalog(400))

    report = Research(api).videos(synthetic_channel.channel_id, VideoQuery(limit=5))

    assert [video.video_id for video in report.items] == [
        f"video-{index:04d}" for index in range(5)
    ]
    assert len(api.scanned) == 105
    assert report.meta.scanned_all is False
    assert report.meta.requests["playlistItems"] == 3


def test_view_ranking_and_unbounded_listing_still_scan_the_whole_catalog(
    synthetic_channel: Channel,
) -> None:
    api = FakeYouTubeAPI(synthetic_channel, catalog(120))

    report = Research(api).videos(
        synthetic_channel.channel_id,
        VideoQuery(sort=SortOrder.VIEWS, limit=5),
        command="videos.top",
    )

    assert len(api.scanned) == 120
    assert report.meta.scanned_all is True
    assert report.meta.matched == 120


def test_missing_statistics_and_unavailable_uploads_generate_warnings(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    api = FakeYouTubeAPI(synthetic_channel, synthetic_videos)
    uploads = api.iter_uploads

    def with_unavailable_upload(playlist_id: str) -> Iterator[UploadItem]:
        yield from uploads(playlist_id)
        yield UploadItem(video_id="unavailable", title="Private video")

    api.iter_uploads = with_unavailable_upload  # type: ignore[assignment]

    report = Research(api).videos("@exampleobservatory", VideoQuery())

    assert len(report.items) == 2
    assert any("1 upload" in warning for warning in report.meta.warnings)
    assert any("like counts" in warning for warning in report.meta.warnings)
    assert any("comment counts" in warning for warning in report.meta.warnings)


def test_analysis_aggregates_all_matches_and_limits_only_breakouts(
    synthetic_channel: Channel,
) -> None:
    videos = [
        Video(
            video_id="a-1",
            title="A",
            url="https://www.youtube.com/watch?v=a-1",
            published_at=datetime(2025, 1, 2, tzinfo=UTC),
            duration_seconds=10,
            views=100,
            likes=10,
            comments=2,
        ),
        Video(
            video_id="a-2",
            title="B",
            url="https://www.youtube.com/watch?v=a-2",
            published_at=datetime(2025, 2, 2, tzinfo=UTC),
            duration_seconds=30,
            views=300,
            likes=30,
            comments=3,
        ),
        Video(
            video_id="a-3",
            title="C",
            url="https://www.youtube.com/watch?v=a-3",
            published_at=datetime(2025, 3, 5, tzinfo=UTC),
            duration_seconds=50,
            views=600,
            likes=None,
            comments=None,
        ),
    ]

    report = Research(FakeYouTubeAPI(synthetic_channel, videos)).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(
            date_from=date(2025, 1, 1),
            date_to=date(2025, 4, 1),
            limit=1,
        ),
    )

    assert report.meta.matched == 3
    assert report.meta.returned == 1
    assert report.meta.truncated is True
    assert report.summary.video_count == 3
    assert report.summary.total_views == 1000
    assert report.summary.median_views == 300
    assert report.summary.coverage.likes == 2
    assert report.summary.coverage.comments == 2
    assert report.summary.coverage.duration == 3
    assert report.summary.coverage.like_rate == 2
    assert report.summary.coverage.comment_rate == 2
    assert report.summary.like_rate == 40 / 400
    assert report.summary.comment_rate == 5 / 400
    assert [cohort.month for cohort in report.monthly_cohorts] == [
        "2025-01",
        "2025-02",
        "2025-03",
        "2025-04",
    ]
    assert report.monthly_cohorts[-1].video_count == 0


def test_analysis_limit_does_not_stop_traversal_and_reports_request_counts(
    synthetic_channel: Channel,
) -> None:
    api = FakeYouTubeAPI(synthetic_channel, catalog(120))

    report = Research(api).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(limit=1),
    )

    assert len(api.scanned) == 120
    assert report.meta.scanned_all is True
    assert report.meta.requests == {"channels": 1, "playlistItems": 3, "videos": 1}
    assert report.meta.returned == 1
    assert report.meta.truncated is True


def test_analysis_includes_zero_upload_months_even_when_empty(
    synthetic_channel: Channel,
) -> None:
    videos = [
        Video(
            video_id="jan",
            title="January",
            url="https://www.youtube.com/watch?v=jan",
            published_at=datetime(2025, 1, 15, tzinfo=UTC),
            views=10,
        ),
        Video(
            video_id="mar",
            title="March",
            url="https://www.youtube.com/watch?v=mar",
            published_at=datetime(2025, 3, 15, tzinfo=UTC),
            views=20,
        ),
    ]
    research = Research(FakeYouTubeAPI(synthetic_channel, videos))

    report = research.analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(date_from=date(2025, 1, 1), date_to=date(2025, 3, 31)),
    )
    empty = research.analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(date_from=date(2030, 1, 1), date_to=date(2030, 3, 31)),
    )

    assert [cohort.video_count for cohort in report.monthly_cohorts] == [1, 0, 1]
    assert report.summary.uploads_per_month == 2 / 3
    assert empty.summary.video_count == 0
    assert empty.summary.uploads_per_month == 0
    assert [cohort.month for cohort in empty.monthly_cohorts] == [
        "2030-01",
        "2030-02",
        "2030-03",
    ]
    assert all(cohort.video_count == 0 for cohort in empty.monthly_cohorts)


def test_analysis_open_ended_cadence_uses_matching_publication_span(
    synthetic_channel: Channel,
) -> None:
    videos = [
        Video(
            video_id=f"open-{year}",
            title="Open window",
            url=f"https://www.youtube.com/watch?v=open-{year}",
            published_at=datetime(year, 1, 1, tzinfo=UTC),
            views=10,
        )
        for year in (2024, 2025)
    ]

    report = Research(FakeYouTubeAPI(synthetic_channel, videos)).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(date_to=date(2025, 12, 31)),
    )

    assert report.summary.uploads_per_month == pytest.approx(2 / 12, rel=1e-3)


def test_analysis_breakouts_normalize_by_publication_year_and_tie_break(
    synthetic_channel: Channel,
) -> None:
    values = [
        ("old", 2024, 10, 1),
        ("new", 2024, 30, 3),
        ("same", 2024, 20, 2),
        ("other", 2025, 100, 4),
        ("other-low", 2025, 50, 5),
    ]
    videos = [
        Video(
            video_id=video_id,
            title=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            published_at=datetime(year, 1, day, tzinfo=UTC),
            views=views,
        )
        for video_id, year, views, day in values
    ]

    report = Research(FakeYouTubeAPI(synthetic_channel, videos)).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(limit=10),
    )

    assert [video.video_id for video in report.items] == [
        "new",
        "other",
        "same",
        "other-low",
        "old",
    ]
    assert report.items[0].year_median_views == 20
    assert report.items[0].year_cohort_size == 3
    assert report.items[0].view_multiplier == 1.5


def test_unscored_videos_do_not_mark_breakout_results_as_truncated(
    synthetic_channel: Channel,
) -> None:
    video = Video(
        video_id="missing-views",
        title="Missing views",
        url="https://www.youtube.com/watch?v=missing-views",
        published_at=datetime(2025, 1, 1, tzinfo=UTC),
        views=None,
    )

    report = Research(FakeYouTubeAPI(synthetic_channel, [video])).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(),
    )

    assert report.meta.matched == 1
    assert report.meta.returned == 0
    assert report.meta.truncated is False


def test_analysis_filters_title_before_aggregating(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    report = Research(FakeYouTubeAPI(synthetic_channel, synthetic_videos)).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(match="CAFÉ", date_from=date(2025, 1, 1), date_to=date(2025, 12, 31)),
    )

    assert report.summary.video_count == 1
    assert report.summary.total_views == 100
    assert [video.video_id for video in report.items] == ["video-a"]


def test_analysis_cadence_uses_elapsed_months_for_same_day_year_window(
    synthetic_channel: Channel,
) -> None:
    videos = [
        Video(
            video_id=f"month-{index}",
            title="Monthly",
            url=f"https://www.youtube.com/watch?v=month-{index}",
            published_at=datetime(
                2025 + ((8 + index) // 12), ((8 + index) % 12) + 1, 3, tzinfo=UTC
            ),
            views=1,
        )
        for index in range(12)
    ]
    report = Research(FakeYouTubeAPI(synthetic_channel, videos)).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(date_from=date(2025, 9, 3), date_to=date(2026, 9, 3)),
    )

    assert report.summary.uploads_per_month == pytest.approx(12 / 12, rel=1e-3)


def test_video_year_9999_does_not_overflow_upper_bound(
    synthetic_channel: Channel,
) -> None:
    video = Video(
        video_id="last-year",
        title="The last year",
        url="https://www.youtube.com/watch?v=last-year",
        published_at=datetime(9999, 1, 1, tzinfo=UTC),
        views=1,
    )

    report = Research(FakeYouTubeAPI(synthetic_channel, [video])).videos(
        synthetic_channel.channel_id,
        VideoQuery(year=9999),
    )

    assert [item.video_id for item in report.items] == ["last-year"]


def test_analysis_maximum_date_does_not_overflow_upper_bound(
    synthetic_channel: Channel,
) -> None:
    video = Video(
        video_id="last-date",
        title="The last date",
        url="https://www.youtube.com/watch?v=last-date",
        published_at=datetime(9999, 12, 31, tzinfo=UTC),
        views=1,
    )

    report = Research(FakeYouTubeAPI(synthetic_channel, [video])).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(date_from=date(9999, 1, 1), date_to=date.max),
    )

    assert [item.video_id for item in report.items] == ["last-date"]
    assert report.monthly_cohorts[-1].month == "9999-12"


def test_analysis_rates_require_positive_views_and_breakouts_skip_unusable_years(
    synthetic_channel: Channel,
) -> None:
    videos = [
        Video(
            video_id="paired",
            title="Paired",
            url="https://www.youtube.com/watch?v=paired",
            published_at=datetime(2024, 1, 1, tzinfo=UTC),
            views=100,
            likes=10,
            comments=2,
        ),
        Video(
            video_id="zero",
            title="Zero views",
            url="https://www.youtube.com/watch?v=zero",
            published_at=datetime(2024, 1, 2, tzinfo=UTC),
            views=0,
            likes=90,
            comments=9,
        ),
        Video(
            video_id="unknown",
            title="Unknown views",
            url="https://www.youtube.com/watch?v=unknown",
            published_at=datetime(2024, 1, 3, tzinfo=UTC),
            views=None,
            likes=80,
            comments=8,
        ),
        Video(
            video_id="missing-count",
            title="Missing count",
            url="https://www.youtube.com/watch?v=missing-count",
            published_at=datetime(2024, 1, 4, tzinfo=UTC),
            views=200,
            likes=None,
            comments=None,
        ),
        Video(
            video_id="all-zero-a",
            title="All zero A",
            url="https://www.youtube.com/watch?v=all-zero-a",
            published_at=datetime(2025, 1, 1, tzinfo=UTC),
            views=0,
        ),
        Video(
            video_id="all-zero-b",
            title="All zero B",
            url="https://www.youtube.com/watch?v=all-zero-b",
            published_at=datetime(2025, 1, 2, tzinfo=UTC),
            views=0,
        ),
    ]

    report = Research(FakeYouTubeAPI(synthetic_channel, videos)).analyze(
        synthetic_channel.channel_id,
        AnalysisQuery(limit=20),
    )

    assert report.summary.like_rate == 10 / 100
    assert report.summary.comment_rate == 2 / 100
    assert report.summary.coverage.likes == 3
    assert report.summary.coverage.comments == 3
    assert [item.video_id for item in report.items] == [
        "missing-count",
        "paired",
        "zero",
    ]
    assert all(item.video_id != "unknown" for item in report.items)
    assert all(item.published_at.year != 2025 for item in report.items)
