"""Small SQLite cache for stable channel identity data."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from platformdirs import user_cache_path

from .models import Channel


class ChannelCache:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = (
            Path(path) if path is not None else user_cache_path("yt-research") / "channels.sqlite3"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_aliases (
                    alias TEXT PRIMARY KEY COLLATE NOCASE,
                    channel_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    handle TEXT,
                    uploads_playlist_id TEXT NOT NULL
                )
                """
            )

    def get(self, alias: str) -> Channel | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT channel_id, title, handle, uploads_playlist_id
                   FROM channel_aliases WHERE alias = ?""",
                (alias.strip(),),
            ).fetchone()
        if row is None:
            return None
        return Channel(
            channel_id=row["channel_id"],
            title=row["title"],
            handle=row["handle"],
            url=f"https://www.youtube.com/channel/{row['channel_id']}",
            uploads_playlist_id=row["uploads_playlist_id"],
        )

    def put(self, alias: str, channel: Channel) -> None:
        aliases = {alias.strip(), channel.channel_id}
        if channel.handle:
            aliases.add(channel.handle)
            aliases.add(f"https://www.youtube.com/{channel.handle}")
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                INSERT INTO channel_aliases(
                    alias, channel_id, title, handle, uploads_playlist_id
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(alias) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    title=excluded.title,
                    handle=excluded.handle,
                    uploads_playlist_id=excluded.uploads_playlist_id
                """,
                [
                    (
                        value,
                        channel.channel_id,
                        channel.title,
                        channel.handle,
                        channel.uploads_playlist_id,
                    )
                    for value in aliases
                    if value
                ],
            )

    def clear(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM channel_aliases")
