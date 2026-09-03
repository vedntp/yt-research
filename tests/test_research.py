from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from yt_research.cache import ChannelCache
from yt_research.models import (
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
