from __future__ import annotations

from pathlib import Path

from yt_research.cache import ChannelCache
from yt_research.models import Channel


def test_cache_round_trip_uses_aliases_case_insensitively(
    tmp_path: Path, synthetic_channel: Channel
) -> None:
    cache = ChannelCache(tmp_path / "cache.sqlite3")
    cache.put("@ExampleObservatory", synthetic_channel)

    cached = cache.get("@exampleobservatory")

    assert cached is not None
    assert cached.channel_id == synthetic_channel.channel_id
    assert cached.uploads_playlist_id == synthetic_channel.uploads_playlist_id
    assert cached.subscribers is None


def test_cache_stores_id_handle_and_url_aliases(tmp_path: Path, synthetic_channel: Channel) -> None:
    cache = ChannelCache(tmp_path / "cache.sqlite3")
    cache.put("@exampleobservatory", synthetic_channel)

    assert cache.get(synthetic_channel.channel_id) is not None
    assert cache.get("@exampleobservatory") is not None
    assert cache.get("https://www.youtube.com/@exampleobservatory") is not None


def test_cache_clear_removes_entries(tmp_path: Path, synthetic_channel: Channel) -> None:
    cache = ChannelCache(tmp_path / "cache.sqlite3")
    cache.put("@exampleobservatory", synthetic_channel)

    cache.clear()

    assert cache.get("@exampleobservatory") is None
