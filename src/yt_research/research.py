"""High-level research operations over the YouTube adapter."""

from __future__ import annotations

import heapq
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol

from .cache import ChannelCache
from .errors import NotFoundError
from .models import (
    Channel,
    ChannelCandidate,
    ChannelReport,
    ReportMeta,
    SortOrder,
    UploadItem,
    Video,
    VideoQuery,
    VideoReport,
)

# Uploads playlists are ordered newest first, but a backdated or republished
# upload can sit out of order. Keep reading this many consecutive uploads older
# than the cutoff before trusting that nothing newer remains.
_ORDER_GRACE = 100


class YouTubeAPI(Protocol):
    @property
    def request_counts(self) -> Mapping[str, int]: ...

    def resolve_channel(self, reference: str) -> Channel: ...

    def search_channels(self, query: str, limit: int = 10) -> list[ChannelCandidate]: ...

    def iter_uploads(self, playlist_id: str) -> Iterator[UploadItem]: ...

    def get_videos(self, video_ids: list[str]) -> list[Video]: ...


@dataclass
class _UploadScan:
    """Uploads worth hydrating, plus how much of the playlist was read."""

    video_ids: list[str] = field(default_factory=list)
    unavailable: int = 0
    complete: bool = True


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _floor(query: VideoQuery) -> datetime | None:
    if query.year is not None:
        return _start_of_day(date(query.year, 1, 1))
    return _start_of_day(query.date_from) if query.date_from else None


def _ceiling(query: VideoQuery) -> datetime | None:
    if query.year is not None:
        return _start_of_day(date(query.year + 1, 1, 1))
    return _start_of_day(query.date_to) + timedelta(days=1) if query.date_to else None


def _counter_delta(before: Mapping[str, int], after: Mapping[str, int]) -> dict[str, int]:
    keys = before.keys() | after.keys()
    return {
        key: after.get(key, 0) - before.get(key, 0)
        for key in keys
        if after.get(key, 0) > before.get(key, 0)
    }


class Research:
    """Deep interface that owns resolution, traversal, filtering, and reporting."""

    def __init__(self, api: YouTubeAPI, cache: ChannelCache | None = None) -> None:
        self.api = api
        self.cache = cache

    def _resolve_channel(self, reference: str, refresh: bool) -> Channel:
        cached = None if refresh or self.cache is None else self.cache.get(reference)
        # Resolve the cached ID to refresh mutable channel statistics while avoiding
        # repeating handle or URL interpretation.
        channel = self.api.resolve_channel(cached.channel_id if cached else reference)
        if not channel.uploads_playlist_id:
            raise NotFoundError(f"channel has no uploads playlist: {reference}")
        if self.cache is not None:
            self.cache.put(reference, channel)
        return channel

    def channel(self, reference: str, *, refresh: bool = False) -> ChannelReport:
        before = dict(self.api.request_counts)
        channel = self._resolve_channel(reference, refresh)
        return ChannelReport(
            channel=channel,
            query={"reference": reference, "refresh": refresh},
            meta=ReportMeta(requests=_counter_delta(before, self.api.request_counts)),
        )

    def search_channels(self, query: str, *, limit: int = 10) -> list[ChannelCandidate]:
        return self.api.search_channels(query, limit)

    def videos(
        self,
        reference: str,
        query: VideoQuery,
        *,
        command: str = "videos.list",
        refresh: bool = False,
    ) -> VideoReport:
        before = dict(self.api.request_counts)
        channel = self._resolve_channel(reference, refresh)
        scan = self._scan_uploads(channel.uploads_playlist_id, query)
        videos = self.api.get_videos(scan.video_ids) if scan.video_ids else []
        warnings = self._warnings(scan, videos)
        matches = self._filter(videos, query)
        matched_count = len(matches)
        ordered = self._sort(matches, query.sort)
        returned = ordered[: query.limit] if query.limit is not None else ordered
        return VideoReport(
            command=command,
            fetched_at=datetime.now(UTC),
            channel=channel,
            query=query,
            items=returned,
            meta=ReportMeta(
                matched=matched_count,
                returned=len(returned),
                requests=_counter_delta(before, self.api.request_counts),
                warnings=warnings,
                truncated=len(returned) < matched_count,
                scanned_all=scan.complete,
            ),
        )

    def _scan_uploads(self, playlist_id: str, query: VideoQuery) -> _UploadScan:
        """Select the uploads that can still reach the result set.

        Playlist metadata already answers the title and date filters, so only
        surviving uploads cost a `videos` request. When the result set is the
        newest N uploads, traversal also stops once the playlist runs older than
        the Nth candidate found so far.
        """

        needle = query.match_text.casefold() if query.match_text else None
        floor, ceiling = _floor(query), _ceiling(query)
        rank_limit = query.limit if query.sort == SortOrder.PUBLISHED_DESC else None
        newest: list[datetime] = []
        scan = _UploadScan()
        stale = 0
        for upload in self.api.iter_uploads(playlist_id):
            if upload.published_at is None:
                scan.unavailable += 1
                continue
            published = upload.published_at.astimezone(UTC)
            ranked = newest[0] if rank_limit is not None and len(newest) == rank_limit else None
            bounds = [bound for bound in (floor, ranked) if bound is not None]
            if bounds and published < max(bounds):
                stale += 1
                if stale >= _ORDER_GRACE:
                    scan.complete = False
                    break
                continue
            stale = 0
            if ceiling is not None and published >= ceiling:
                continue
            if needle is not None and needle not in upload.title.casefold():
                continue
            scan.video_ids.append(upload.video_id)
            if rank_limit is not None:
                heapq.heappush(newest, published)
                if len(newest) > rank_limit:
                    heapq.heappop(newest)
        return scan

    @staticmethod
    def _filter(videos: list[Video], query: VideoQuery) -> list[Video]:
        result: list[Video] = []
        needle = query.match_text.casefold() if query.match_text else None
        for video in videos:
            published = video.published_at.astimezone(UTC).date()
            if needle and needle not in video.title.casefold():
                continue
            if query.year is not None and published.year != query.year:
                continue
            if query.date_from is not None and published < query.date_from:
                continue
            if query.date_to is not None and published > query.date_to:
                continue
            result.append(video)
        return result

    @staticmethod
    def _sort(videos: list[Video], order: SortOrder) -> list[Video]:
        if order == SortOrder.PUBLISHED_ASC:
            return sorted(videos, key=lambda video: (video.published_at, video.video_id))
        if order == SortOrder.PUBLISHED_DESC:
            return sorted(
                videos,
                key=lambda video: (video.published_at, video.video_id),
                reverse=True,
            )
        field = "views" if order == SortOrder.VIEWS else "likes"
        return sorted(
            videos,
            key=lambda video: (
                getattr(video, field) is not None,
                getattr(video, field) or 0,
                video.published_at,
                video.video_id,
            ),
            reverse=True,
        )

    @staticmethod
    def _warnings(scan: _UploadScan, videos: list[Video]) -> list[str]:
        warnings: list[str] = []
        missing = len(scan.video_ids) - len(videos) + scan.unavailable
        if missing:
            warnings.append(f"{missing} upload(s) were unavailable or returned incomplete metadata")
        missing_likes = sum(video.likes is None for video in videos)
        missing_comments = sum(video.comments is None for video in videos)
        if missing_likes:
            warnings.append(f"like counts were unavailable for {missing_likes} video(s)")
        if missing_comments:
            warnings.append(f"comment counts were unavailable for {missing_comments} video(s)")
        return warnings
