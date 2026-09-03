from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from yt_research.errors import AmbiguousChannelError, CredentialsError, QuotaError
from yt_research.youtube import YouTubeClient

BASE_URL = "https://www.googleapis.com/youtube/v3"


def channel_payload() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "UC000000000000000000001",
                "snippet": {
                    "title": "Example &amp; Observatory",
                    "description": "Synthetic &lt;data&gt;",
                    "customUrl": "@exampleobservatory",
                    "publishedAt": "2020-01-02T03:04:05Z",
                },
                "contentDetails": {"relatedPlaylists": {"uploads": "UU000000000000000000001"}},
                "statistics": {
                    "subscriberCount": "1234",
                    "videoCount": "60",
                    "viewCount": "9999",
                },
            }
        ]
    }


def video_item(index: int, *, likes: str | None = "3") -> dict[str, object]:
    statistics: dict[str, str] = {"viewCount": str(index * 10), "commentCount": "2"}
    if likes is not None:
        statistics["likeCount"] = likes
    return {
        "id": f"video-{index}",
        "snippet": {
            "title": f"Lesson &amp; Sample {index}",
            "description": "Synthetic fixture",
            "publishedAt": "2025-02-03T04:05:06Z",
            "channelId": "UC000000000000000000001",
        },
        "contentDetails": {"duration": "PT1H2M3S"},
        "statistics": statistics,
    }


@respx.mock
def test_resolve_handle_and_channel_url() -> None:
    route = respx.get(f"{BASE_URL}/channels").mock(
        return_value=httpx.Response(200, json=channel_payload())
    )
    client = YouTubeClient("synthetic-secret")

    channel = client.resolve_channel("https://www.youtube.com/@exampleobservatory")

    assert channel.title == "Example & Observatory"
    assert channel.description == "Synthetic <data>"
    assert channel.uploads_playlist_id == "UU000000000000000000001"
    assert channel.subscribers == 1234
    assert route.calls[0].request.url.params["forHandle"] == "exampleobservatory"
    assert route.calls[0].request.url.params["key"] == "synthetic-secret"


@respx.mock
def test_resolve_international_handle_url() -> None:
    route = respx.get(f"{BASE_URL}/channels").mock(
        return_value=httpx.Response(200, json=channel_payload())
    )
    client = YouTubeClient("synthetic-secret")

    client.resolve_channel("https://www.youtube.com/@クリエイター")

    assert route.calls[0].request.url.params["forHandle"] == "クリエイター"


def test_plain_channel_name_is_rejected_without_network_request() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    client = YouTubeClient("synthetic-secret", transport=transport)

    with pytest.raises(AmbiguousChannelError, match="channel search"):
        client.resolve_channel("Example Observatory")


@respx.mock
def test_upload_iterator_traverses_every_page() -> None:
    route = respx.get(f"{BASE_URL}/playlistItems").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {"title": "Lesson &amp; Sample 1"},
                            "contentDetails": {
                                "videoId": "video-1",
                                "videoPublishedAt": "2026-01-02T00:00:00Z",
                            },
                        }
                    ],
                    "nextPageToken": "next-page",
                },
            ),
            httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {"title": "Private video"},
                            "contentDetails": {"videoId": "video-2"},
                        }
                    ]
                },
            ),
        ]
    )
    client = YouTubeClient("synthetic-secret")

    uploads = list(client.iter_uploads("UU000000000000000000001"))

    assert [upload.video_id for upload in uploads] == ["video-1", "video-2"]
    assert uploads[0].title == "Lesson & Sample 1"
    assert uploads[0].published_at == datetime(2026, 1, 2, tzinfo=UTC)
    assert uploads[1].published_at is None
    assert len(route.calls) == 2
    assert "pageToken" not in route.calls[0].request.url.params
    assert route.calls[1].request.url.params["pageToken"] == "next-page"


@respx.mock
def test_video_requests_batch_more_than_50_ids_and_combine_responses() -> None:
    route = respx.get(f"{BASE_URL}/videos").mock(
        side_effect=[
            httpx.Response(200, json={"items": [video_item(index) for index in range(50)]}),
            httpx.Response(200, json={"items": [video_item(50), video_item(51, likes=None)]}),
        ]
    )
    client = YouTubeClient("synthetic-secret")

    videos = client.get_videos([f"video-{index}" for index in range(52)])

    assert len(videos) == 52
    assert len(route.calls[0].request.url.params["id"].split(",")) == 50
    assert route.calls[1].request.url.params["id"] == "video-50,video-51"
    assert videos[0].title == "Lesson & Sample 0"
    assert videos[0].duration_seconds == 3723
    assert videos[-1].likes is None


@respx.mock
def test_retryable_response_uses_exponential_backoff() -> None:
    route = respx.get(f"{BASE_URL}/channels").mock(
        side_effect=[
            httpx.Response(503, json={"error": {"message": "temporary"}}),
            httpx.Response(429, json={"error": {"message": "slow down"}}),
            httpx.Response(200, json=channel_payload()),
        ]
    )
    delays: list[float] = []
    client = YouTubeClient("synthetic-secret", sleep=delays.append)

    client.resolve_channel("@exampleobservatory")

    assert len(route.calls) == 3
    assert delays == [0.5, 1.0]


@respx.mock
def test_quota_error_is_mapped_after_retries() -> None:
    error = {"error": {"message": "quota exhausted", "errors": [{"reason": "quotaExceeded"}]}}
    respx.get(f"{BASE_URL}/channels").mock(return_value=httpx.Response(403, json=error))
    client = YouTubeClient("synthetic-secret", sleep=lambda _: None)

    with pytest.raises(QuotaError, match="quota exhausted"):
        client.resolve_channel("@exampleobservatory")


@respx.mock
def test_invalid_key_fails_immediately_without_exposing_secret() -> None:
    error = {"error": {"message": "invalid credential", "errors": [{"reason": "keyInvalid"}]}}
    route = respx.get(f"{BASE_URL}/channels").mock(return_value=httpx.Response(403, json=error))
    client = YouTubeClient("never-print-this-secret")

    with pytest.raises(CredentialsError) as captured:
        client.resolve_channel("@exampleobservatory")

    assert len(route.calls) == 1
    assert "never-print-this-secret" not in str(captured.value)


@respx.mock
def test_invalid_key_with_http_400_is_a_credentials_failure() -> None:
    error = {"error": {"message": "invalid credential", "errors": [{"reason": "keyInvalid"}]}}
    respx.get(f"{BASE_URL}/channels").mock(return_value=httpx.Response(400, json=error))
    client = YouTubeClient("synthetic-secret")

    with pytest.raises(CredentialsError, match="invalid credential"):
        client.resolve_channel("@exampleobservatory")


@respx.mock
def test_channel_search_is_explicit_and_bounded() -> None:
    response = {
        "items": [
            {
                "id": {"channelId": "UC000000000000000000002"},
                "snippet": {"title": "Fictional &amp; Candidate", "description": "Synthetic"},
            }
        ]
    }
    route = respx.get(f"{BASE_URL}/search").mock(return_value=httpx.Response(200, json=response))
    client = YouTubeClient("synthetic-secret")

    candidates = client.search_channels("fictional query", limit=500)

    assert candidates[0].title == "Fictional & Candidate"
    assert route.calls[0].request.url.params["maxResults"] == "50"
    assert client.request_counts == {"search": 1}


@respx.mock
def test_invalid_json_is_an_upstream_failure() -> None:
    from yt_research.errors import UpstreamError

    respx.get(f"{BASE_URL}/channels").mock(
        return_value=httpx.Response(
            200, content=b"not-json", headers={"content-type": "text/plain"}
        )
    )
    client = YouTubeClient("synthetic-secret")

    with pytest.raises(UpstreamError, match="invalid JSON"):
        client.resolve_channel("@exampleobservatory")


def test_fixture_payloads_are_valid_json() -> None:
    assert json.loads(json.dumps(channel_payload()))["items"]
