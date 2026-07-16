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


class ReportMeta(BaseModel):
    matched: int = 0
    returned: int = 0
    requests: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    truncated: bool = False


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
