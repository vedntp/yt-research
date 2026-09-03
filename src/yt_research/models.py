"""Public, serializable data models used by the research engine."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SortOrder(StrEnum):
    PUBLISHED_ASC = "published-asc"
    PUBLISHED_DESC = "published-desc"
    VIEWS = "views"
    LIKES = "likes"


class Channel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channel_id: str
    title: str
    handle: str | None = None
    description: str | None = None
    url: str
    uploads_playlist_id: str
    published_at: datetime | None = None
    subscribers: int | None = None
    video_count: int | None = None
    views: int | None = None


class ChannelCandidate(BaseModel):
    channel_id: str
    title: str
    handle: str | None = None
    description: str | None = None
    url: str


class Video(BaseModel):
    video_id: str
    title: str
    url: str
    published_at: datetime
    duration_seconds: int | None = None
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    description: str | None = None
    channel_id: str | None = None


class UploadItem(BaseModel):
    """Cheap upload descriptor available from a playlist page."""

    video_id: str
    title: str
    published_at: datetime | None = None


class VideoQuery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    match_text: str | None = Field(default=None, alias="match")
    year: int | None = Field(default=None, ge=1970, le=9999)
    date_from: date | None = Field(default=None, alias="from")
    date_to: date | None = Field(default=None, alias="to")
    sort: SortOrder = SortOrder.PUBLISHED_DESC
    limit: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_dates(self) -> VideoQuery:
        if self.year is not None and (self.date_from is not None or self.date_to is not None):
            raise ValueError("year cannot be combined with from or to")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("from cannot be later than to")
        return self


class AnalysisQuery(BaseModel):
    """Filters and presentation options for a channel analysis report.

    The command layer resolves relative windows (for example ``--months 12``)
    into inclusive UTC calendar dates before constructing this model.  Leaving
    both dates unset represents an unbounded history query, which is useful for
    callers of :meth:`yt_research.research.Research.analyze` and for the
    command's ``--all`` option.
    """

    model_config = ConfigDict(populate_by_name=True)

    match_text: str | None = Field(default=None, alias="match")
    date_from: date | None = Field(default=None, alias="from")
    date_to: date | None = Field(default=None, alias="to")
    limit: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def validate_dates(self) -> AnalysisQuery:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("from cannot be later than to")
        return self


class ReportMeta(BaseModel):
    matched: int = 0
    returned: int = 0
    requests: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False
    scanned_all: bool = True


class ChannelReport(BaseModel):
    schema_version: int = 1
    command: str = "channel.info"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: Channel
    query: dict[str, Any] = Field(default_factory=dict)
    items: list[Any] = Field(default_factory=list)
    meta: ReportMeta = Field(default_factory=ReportMeta)


class VideoReport(BaseModel):
    schema_version: int = 1
    command: str = "videos.list"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: Channel
    query: VideoQuery
    items: list[Video] = Field(default_factory=list)
    meta: ReportMeta = Field(default_factory=ReportMeta)


class AnalysisCoverage(BaseModel):
    """Number of analyzed videos carrying each metric."""

    views: int = 0
    likes: int = 0
    comments: int = 0
    duration: int = 0
    like_rate: int = 0
    comment_rate: int = 0


class AnalysisSummary(BaseModel):
    """Aggregate current metrics for all videos matching an analysis query."""

    video_count: int = 0
    published_from: date | None = None
    published_to: date | None = None
    total_views: int = 0
    median_views: float | None = None
    median_likes: float | None = None
    median_comments: float | None = None
    median_duration_seconds: float | None = None
    like_rate: float | None = None
    comment_rate: float | None = None
    uploads_per_month: float | None = None
    median_days_between_uploads: float | None = None
    coverage: AnalysisCoverage = Field(default_factory=AnalysisCoverage)


class MonthlyCohort(BaseModel):
    """Current performance grouped by the month in which videos were published."""

    month: str
    video_count: int = 0
    total_views: int = 0
    median_views: float | None = None
    like_rate: float | None = None
    comment_rate: float | None = None
    median_duration_seconds: float | None = None


class BreakoutVideo(Video):
    """A video whose current views are high relative to its publication year."""

    year_median_views: float
    year_cohort_size: int
    view_multiplier: float


class AnalysisReport(BaseModel):
    schema_version: int = 1
    command: str = "channel.analyze"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    channel: Channel
    query: AnalysisQuery
    summary: AnalysisSummary
    monthly_cohorts: list[MonthlyCohort] = Field(default_factory=list)
    items: list[BreakoutVideo] = Field(default_factory=list)
    meta: ReportMeta = Field(default_factory=ReportMeta)
