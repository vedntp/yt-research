"""Narrow HTTP adapter for the public YouTube Data API v3."""

from __future__ import annotations

import html
import re
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from datetime import datetime
from typing import Any, cast
from urllib.parse import unquote, urlparse

import httpx

from .errors import CredentialsError, NetworkError, NotFoundError, QuotaError, UpstreamError
from .models import Channel, ChannelCandidate, UploadItem, Video

_CHANNEL_ID = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
_HANDLE = re.compile(r"^@[^\s/@?&#]+$")
_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _duration_seconds(value: str | None) -> int | None:
    if not value:
        return None
    match = _DURATION.fullmatch(value)
    if match is None:
        return None
    parts = {key: int(number or 0) for key, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _channel_selector(reference: str) -> tuple[str, str]:
    reference = reference.strip()
    if _CHANNEL_ID.fullmatch(reference):
        return "id", reference
    if _HANDLE.fullmatch(reference):
        return "forHandle", reference[1:]
    parsed = urlparse(reference if "://" in reference else f"https://{reference}")
    if parsed.netloc.lower() in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] == "channel" and _CHANNEL_ID.fullmatch(parts[1]):
            return "id", parts[1]
        if parts and _HANDLE.fullmatch(parts[0]):
            return "forHandle", parts[0][1:]
    raise ValueError("channel reference must be a channel ID, @handle, or canonical channel URL")


class YouTubeClient:
    """YouTube adapter with bounded retrying and observable request counts."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://www.googleapis.com/youtube/v3",
        timeout: float = 20.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise CredentialsError("a YouTube Data API key is required")
        self._api_key = api_key
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._sleep = sleep
        self._requests: Counter[str] = Counter()

    @property
    def request_counts(self) -> dict[str, int]:
        return dict(self._requests)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> YouTubeClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(4):
            self._requests[endpoint] += 1
            try:
                response = self._client.get(f"/{endpoint}", params={**params, "key": self._api_key})
            except httpx.RequestError as error:
                if attempt < 3:
                    self._sleep(0.5 * (2**attempt))
                    continue
                # Do not include the exception text because HTTPX may include the
                # request URL, whose query string contains the API key.
                raise NetworkError(f"YouTube request failed while calling {endpoint}") from error

            if response.status_code < 400:
                try:
                    return cast(dict[str, Any], response.json())
                except ValueError as error:
                    raise UpstreamError("YouTube returned an invalid JSON response") from error

            reason, message = self._error_details(response)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                self._sleep(0.5 * (2**attempt))
                continue
            if reason in {
                "keyInvalid",
                "ipRefererBlocked",
                "accessNotConfigured",
                "forbidden",
            }:
                raise CredentialsError(message)
            quota_reasons = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}
            if reason in quota_reasons or response.status_code == 429:
                raise QuotaError(message)
            if response.status_code == 404:
                raise NotFoundError(message)
            raise UpstreamError(message)
        raise AssertionError("retry loop exhausted")

    @staticmethod
    def _error_details(response: httpx.Response) -> tuple[str, str]:
        try:
            error = response.json().get("error", {})
            details = error.get("errors") or []
            reason = details[0].get("reason", "") if details else ""
            message = error.get("message") or f"YouTube API returned HTTP {response.status_code}"
            return reason, message
        except (ValueError, AttributeError, TypeError):
            return "", f"YouTube API returned HTTP {response.status_code}"

    def resolve_channel(self, reference: str) -> Channel:
        try:
            selector, value = _channel_selector(reference)
        except ValueError as error:
            from .errors import AmbiguousChannelError

            message = f"{error}. Use 'yt-research channel search' for names"
            raise AmbiguousChannelError(message) from error
        payload = self._request(
            "channels",
            {"part": "snippet,contentDetails,statistics", selector: value, "maxResults": 1},
        )
        items = payload.get("items", [])
        if not items:
            raise NotFoundError(f"channel not found: {reference}")
        return self._parse_channel(items[0])

    @staticmethod
    def _parse_channel(item: dict[str, Any]) -> Channel:
        snippet = item.get("snippet", {})
        details = item.get("contentDetails", {})
        statistics = item.get("statistics", {})
        channel_id = item["id"]
        custom_url = snippet.get("customUrl")
        handle = custom_url if isinstance(custom_url, str) and custom_url.startswith("@") else None
        return Channel(
            channel_id=channel_id,
            title=html.unescape(snippet.get("title", "")),
            handle=handle,
            description=html.unescape(snippet.get("description", "")) or None,
            url=f"https://www.youtube.com/channel/{channel_id}",
            uploads_playlist_id=details.get("relatedPlaylists", {}).get("uploads", ""),
            published_at=_parse_datetime(snippet.get("publishedAt")),
            subscribers=(
                None
                if statistics.get("hiddenSubscriberCount")
                else _integer(statistics.get("subscriberCount"))
            ),
            video_count=_integer(statistics.get("videoCount")),
            views=_integer(statistics.get("viewCount")),
        )

    def search_channels(self, query: str, limit: int = 10) -> list[ChannelCandidate]:
        if not query.strip():
            return []
        payload = self._request(
            "search",
            {
                "part": "snippet",
                "type": "channel",
                "q": query,
                "maxResults": max(1, min(limit, 50)),
            },
        )
        candidates: list[ChannelCandidate] = []
        for item in payload.get("items", []):
            channel_id = item.get("id", {}).get("channelId")
            if not channel_id:
                continue
            snippet = item.get("snippet", {})
            candidates.append(
                ChannelCandidate(
                    channel_id=channel_id,
                    title=html.unescape(snippet.get("title", "")),
                    description=html.unescape(snippet.get("description", "")) or None,
                    url=f"https://www.youtube.com/channel/{channel_id}",
                )
            )
        return candidates

    def iter_uploads(self, playlist_id: str) -> Iterator[UploadItem]:
        """Yield uploads newest first, including the title and publication time.

        Playlist pages carry enough metadata to filter without spending a
        `videos` request, and the generator only fetches a page when the caller
        asks for an item beyond the current one.
        """

        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._request("playlistItems", params)
            for item in payload.get("items", []):
                details = item.get("contentDetails", {})
                video_id = details.get("videoId")
                if not video_id:
                    continue
                yield UploadItem(
                    video_id=video_id,
                    title=html.unescape(item.get("snippet", {}).get("title", "")),
                    published_at=_parse_datetime(details.get("videoPublishedAt")),
                )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

    def get_videos(self, video_ids: Sequence[str]) -> list[Video]:
        videos: list[Video] = []
        for offset in range(0, len(video_ids), 50):
            batch = video_ids[offset : offset + 50]
            if not batch:
                continue
            payload = self._request(
                "videos",
                {
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(batch),
                    "maxResults": 50,
                },
            )
            for item in payload.get("items", []):
                parsed = self._parse_video(item)
                if parsed is not None:
                    videos.append(parsed)
        return videos

    @staticmethod
    def _parse_video(item: dict[str, Any]) -> Video | None:
        snippet = item.get("snippet", {})
        published_at = _parse_datetime(snippet.get("publishedAt"))
        if published_at is None or not item.get("id"):
            return None
        statistics = item.get("statistics", {})
        video_id = item["id"]
        return Video(
            video_id=video_id,
            title=html.unescape(snippet.get("title", "")),
            description=html.unescape(snippet.get("description", "")) or None,
            url=f"https://www.youtube.com/watch?v={video_id}",
            published_at=published_at,
            duration_seconds=_duration_seconds(item.get("contentDetails", {}).get("duration")),
            views=_integer(statistics.get("viewCount")),
            likes=_integer(statistics.get("likeCount")),
            comments=_integer(statistics.get("commentCount")),
            channel_id=snippet.get("channelId"),
        )
