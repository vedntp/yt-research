"""High-level research operations over the YouTube adapter."""

from __future__ import annotations

import calendar
import heapq
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from statistics import median
from typing import Protocol

from .cache import ChannelCache
from .errors import NotFoundError
from .models import (
    AnalysisCoverage,
    AnalysisQuery,
    AnalysisReport,
    AnalysisSummary,
    BreakoutVideo,
    Channel,
    ChannelCandidate,
    ChannelReport,
    MonthlyCohort,
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


@dataclass
class _CollectedVideos:
    """The shared result of resolution, traversal, hydration, and filtering."""

    channel: Channel
    scan: _UploadScan
    videos: list[Video]
    matches: list[Video]
    warnings: list[str]


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


def _floor(query: VideoQuery | AnalysisQuery) -> datetime | None:
    if isinstance(query, VideoQuery) and query.year is not None:
        return _start_of_day(date(query.year, 1, 1))
    return _start_of_day(query.date_from) if query.date_from else None


def _ceiling(query: VideoQuery | AnalysisQuery) -> datetime | None:
    if isinstance(query, VideoQuery) and query.year is not None:
        if query.year == date.max.year:
            # There is no representable midnight on the following year. The
            # year filter still excludes anything outside 9999, so an open
            # upper bound is equivalent and avoids overflowing date().
            return None
        return _start_of_day(date(query.year + 1, 1, 1))
    if query.date_to == date.max:
        return None
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
        collected = self._collect_videos(reference, query, refresh=refresh)
        matches = collected.matches
        matched_count = len(matches)
        ordered = self._sort(matches, query.sort)
        returned = ordered[: query.limit] if query.limit is not None else ordered
        return VideoReport(
            command=command,
            fetched_at=datetime.now(UTC),
            channel=collected.channel,
            query=query,
            items=returned,
            meta=ReportMeta(
                matched=matched_count,
                returned=len(returned),
                requests=_counter_delta(before, self.api.request_counts),
                warnings=collected.warnings,
                truncated=len(returned) < matched_count,
                scanned_all=collected.scan.complete,
            ),
        )

    def analyze(
        self,
        reference: str,
        query: AnalysisQuery,
        *,
        refresh: bool = False,
    ) -> AnalysisReport:
        """Analyze every matching upload in an inclusive date window.

        The query's ``limit`` only controls the breakout list. Collection and
        all aggregate calculations always use every matching upload, so a small
        breakout list cannot silently change the summary or cohort metrics.
        With both dates unset, the effective window is the channel's complete
        upload history; callers that need a rolling default should resolve that
        window before constructing ``AnalysisQuery``.
        """

        before = dict(self.api.request_counts)
        collected = self._collect_videos(reference, query, refresh=refresh)
        matches = collected.matches
        summary = self._analysis_summary(matches, query)
        monthly_cohorts = self._monthly_cohorts(matches, query)
        breakout_candidates = self._breakouts(matches)
        breakouts = breakout_candidates[: query.limit]
        return AnalysisReport(
            channel=collected.channel,
            query=query,
            summary=summary,
            monthly_cohorts=monthly_cohorts,
            items=breakouts,
            meta=ReportMeta(
                matched=len(matches),
                returned=len(breakouts),
                requests=_counter_delta(before, self.api.request_counts),
                warnings=collected.warnings,
                truncated=len(breakouts) < len(breakout_candidates),
                scanned_all=collected.scan.complete,
            ),
        )

    def _collect_videos(
        self,
        reference: str,
        query: VideoQuery | AnalysisQuery,
        *,
        refresh: bool,
    ) -> _CollectedVideos:
        channel = self._resolve_channel(reference, refresh)
        scan = self._scan_uploads(channel.uploads_playlist_id, query)
        videos = self.api.get_videos(scan.video_ids) if scan.video_ids else []
        warnings = self._warnings(scan, videos)
        matches = self._filter(videos, query)
        return _CollectedVideos(
            channel=channel,
            scan=scan,
            videos=videos,
            matches=matches,
            warnings=warnings,
        )

    def _scan_uploads(
        self, playlist_id: str, query: VideoQuery | AnalysisQuery
    ) -> _UploadScan:
        """Select the uploads that can still reach the result set.

        Playlist metadata already answers the title and date filters, so only
        surviving uploads cost a `videos` request. When the result set is the
        newest N uploads, traversal also stops once the playlist runs older than
        the Nth candidate found so far.
        """

        needle = query.match_text.casefold() if query.match_text else None
        floor, ceiling = _floor(query), _ceiling(query)
        # Analysis must hydrate the entire matching cohort. Only the regular
        # newest-video query can use its limit to stop traversal early.
        rank_limit = (
            query.limit
            if isinstance(query, VideoQuery) and query.sort == SortOrder.PUBLISHED_DESC
            else None
        )
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
    def _filter(videos: list[Video], query: VideoQuery | AnalysisQuery) -> list[Video]:
        result: list[Video] = []
        needle = query.match_text.casefold() if query.match_text else None
        for video in videos:
            published = video.published_at.astimezone(UTC).date()
            if needle and needle not in video.title.casefold():
                continue
            if (
                isinstance(query, VideoQuery)
                and query.year is not None
                and published.year != query.year
            ):
                continue
            if query.date_from is not None and published < query.date_from:
                continue
            if query.date_to is not None and published > query.date_to:
                continue
            result.append(video)
        return result

    @staticmethod
    def _median(values: list[int | float]) -> float | None:
        if not values:
            return None
        return float(median(values))

    @staticmethod
    def _rate(videos: list[Video], field: str) -> float | None:
        """Return a weighted engagement rate for paired, positive-view rows."""

        total_views = 0
        total_engagement = 0
        for video in videos:
            views = video.views
            engagement = getattr(video, field)
            if views is None or views <= 0 or engagement is None:
                continue
            total_views += views
            total_engagement += engagement
        return total_engagement / total_views if total_views else None

    @staticmethod
    def _total_views(videos: list[Video]) -> int:
        return sum(video.views for video in videos if video.views is not None)

    @staticmethod
    def _coverage(videos: list[Video]) -> AnalysisCoverage:
        return AnalysisCoverage(
            views=sum(video.views is not None for video in videos),
            likes=sum(video.likes is not None for video in videos),
            comments=sum(video.comments is not None for video in videos),
            duration=sum(video.duration_seconds is not None for video in videos),
            like_rate=sum(
                video.likes is not None and video.views is not None and video.views > 0
                for video in videos
            ),
            comment_rate=sum(
                video.comments is not None and video.views is not None and video.views > 0
                for video in videos
            ),
        )

    @staticmethod
    def _utc_dates(videos: list[Video]) -> list[date]:
        return [video.published_at.astimezone(UTC).date() for video in videos]

    @staticmethod
    def _month_start(value: date) -> date:
        return value.replace(day=1)

    @staticmethod
    def _next_month(value: date) -> date:
        if value.month == 12:
            if value.year == date.max.year:
                return date.max
            return date(value.year + 1, 1, 1)
        return date(value.year, value.month + 1, 1)

    @staticmethod
    def _month_label(value: date) -> str:
        return f"{value.year:04d}-{value.month:02d}"

    @classmethod
    def _month_span(cls, start: date, end: date) -> Iterator[date]:
        """Yield first days of each calendar month in an inclusive span."""

        current = cls._month_start(start)
        finish = cls._month_start(end)
        while current <= finish:
            yield current
            if current.year == date.max.year and current.month == 12:
                break
            current = cls._next_month(current)

    @classmethod
    def _analysis_span(
        cls, matches: list[Video], query: AnalysisQuery
    ) -> tuple[date, date] | None:
        if not matches:
            return None
        dates = cls._utc_dates(matches)
        if query.date_from is not None and query.date_to is not None:
            return query.date_from, query.date_to
        # A single-ended or unbounded query has no complete requested span.
        # Measure cadence across the actual matching publication history.
        return min(dates), max(dates)

    @classmethod
    def _months_in_span(cls, start: date, end: date) -> float:
        """Estimate elapsed calendar months in an inclusive report span.

        Calendar labels are inclusive for cohort display, but using their count
        as the cadence denominator overstates a rolling window that starts and
        ends on the same day (for example, September 3 to September 3 would
        incorrectly touch thirteen labels). Use elapsed days for partial
        months and preserve exact whole-calendar-month windows.
        """

        if start > end:
            return 1.0
        month_delta = (end.year - start.year) * 12 + end.month - start.month
        start_is_month_end = start.day == calendar.monthrange(start.year, start.month)[1]
        end_is_month_end = end.day == calendar.monthrange(end.year, end.month)[1]
        if month_delta > 0 and (start.day == end.day or (start_is_month_end and end_is_month_end)):
            return float(month_delta)
        if start.day == 1 and end.day == calendar.monthrange(end.year, end.month)[1]:
            return float(month_delta + 1)
        return max(1.0, (end - start).days / 30.4375)

    @classmethod
    def _analysis_summary(
        cls, matches: list[Video], query: AnalysisQuery
    ) -> AnalysisSummary:
        dates = cls._utc_dates(matches)
        span = cls._analysis_span(matches, query)
        if span is None and query.date_from is not None and query.date_to is not None:
            # A bounded empty report still has a known cadence denominator;
            # unlike cohorts, its summary can report zero uploads per month.
            span = query.date_from, query.date_to
        ordered_published = sorted(
            video.published_at.astimezone(UTC) for video in matches
        )
        gaps = [
            (later - earlier).total_seconds() / 86400
            for earlier, later in pairwise(ordered_published)
        ]
        uploads_per_month = None
        if span is not None:
            uploads_per_month = len(matches) / cls._months_in_span(*span)
        return AnalysisSummary(
            video_count=len(matches),
            published_from=min(dates) if dates else None,
            published_to=max(dates) if dates else None,
            total_views=cls._total_views(matches),
            median_views=cls._median(
                [video.views for video in matches if video.views is not None]
            ),
            median_likes=cls._median(
                [video.likes for video in matches if video.likes is not None]
            ),
            median_comments=cls._median(
                [video.comments for video in matches if video.comments is not None]
            ),
            median_duration_seconds=cls._median(
                [
                    video.duration_seconds
                    for video in matches
                    if video.duration_seconds is not None
                ]
            ),
            like_rate=cls._rate(matches, "likes"),
            comment_rate=cls._rate(matches, "comments"),
            uploads_per_month=uploads_per_month,
            median_days_between_uploads=(
                float(median(gaps)) if gaps else None
            ),
            coverage=cls._coverage(matches),
        )

    @classmethod
    def _monthly_cohorts(
        cls, matches: list[Video], query: AnalysisQuery
    ) -> list[MonthlyCohort]:
        span = cls._analysis_span(matches, query)
        if span is None and query.date_from is not None and query.date_to is not None:
            span = query.date_from, query.date_to
        if span is None:
            return []
        grouped: dict[str, list[Video]] = {}
        for video in matches:
            month = cls._month_label(video.published_at.astimezone(UTC).date())
            grouped.setdefault(month, []).append(video)

        if query.date_from is not None and query.date_to is not None:
            # A fully bounded report describes the requested calendar span,
            # including months with no uploads. Open-ended and all-history
            # reports only expose observed publication months.
            month_starts = list(cls._month_span(*span))
        else:
            month_starts = [
                date.fromisoformat(f"{month}-01") for month in sorted(grouped)
            ]

        cohorts: list[MonthlyCohort] = []
        for month_start in month_starts:
            month = cls._month_label(month_start)
            videos = grouped.get(month, [])
            cohorts.append(
                MonthlyCohort(
                    month=month,
                    video_count=len(videos),
                    total_views=cls._total_views(videos),
                    median_views=cls._median(
                        [video.views for video in videos if video.views is not None]
                    ),
                    like_rate=cls._rate(videos, "likes"),
                    comment_rate=cls._rate(videos, "comments"),
                    median_duration_seconds=cls._median(
                        [
                            video.duration_seconds
                            for video in videos
                            if video.duration_seconds is not None
                        ]
                    ),
                )
            )
        return cohorts

    @staticmethod
    def _breakouts(matches: list[Video]) -> list[BreakoutVideo]:
        by_year: dict[int, list[int]] = {}
        for video in matches:
            if video.views is None:
                continue
            by_year.setdefault(video.published_at.astimezone(UTC).year, []).append(
                video.views
            )

        year_stats: dict[int, tuple[float, int]] = {}
        for year, views in by_year.items():
            year_median = float(median(views))
            if year_median > 0:
                year_stats[year] = (year_median, len(views))

        scored: list[BreakoutVideo] = []
        for video in matches:
            if video.views is None:
                continue
            stats = year_stats.get(video.published_at.astimezone(UTC).year)
            if stats is None:
                continue
            year_median, cohort_size = stats
            scored.append(
                BreakoutVideo(
                    **video.model_dump(),
                    year_median_views=year_median,
                    year_cohort_size=cohort_size,
                    view_multiplier=video.views / year_median,
                )
            )

        scored.sort(
            key=lambda video: (
                video.view_multiplier,
                video.views if video.views is not None else 0,
                video.published_at,
                video.video_id,
            ),
            reverse=True,
        )
        return scored

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
