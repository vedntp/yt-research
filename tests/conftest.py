from __future__ import annotations

from datetime import UTC, datetime

import pytest

from yt_research.models import Channel, Video


@pytest.fixture
def synthetic_channel() -> Channel:
    return Channel(
        channel_id="UC000000000000000000001",
        title="Example Observatory",
        handle="@exampleobservatory",
        description="A fictional channel used only by the test suite.",
        url="https://www.youtube.com/channel/UC000000000000000000001",
        uploads_playlist_id="UU000000000000000000001",
        subscribers=1200,
        video_count=3,
        views=54000,
    )


@pytest.fixture
def synthetic_videos() -> list[Video]:
    return [
        Video(
            video_id="video-a",
            title="Caf\u00e9 & Telescope",
            url="https://www.youtube.com/watch?v=video-a",
            published_at=datetime(2025, 1, 2, 10, tzinfo=UTC),
            duration_seconds=90,
            views=100,
            likes=10,
            comments=1,
        ),
        Video(
            video_id="video-b",
            title="Synthetic Tutorial",
            url="https://www.youtube.com/watch?v=video-b",
            published_at=datetime(2026, 2, 3, 11, tzinfo=UTC),
            duration_seconds=120,
            views=250,
            likes=None,
            comments=None,
        ),
    ]
