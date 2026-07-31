from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

import yt_research.cli as cli
from yt_research import __version__
from yt_research.errors import NotFoundError
from yt_research.models import (
    Channel,
    ChannelCandidate,
    ChannelReport,
    ReportMeta,
    Video,
    VideoQuery,
    VideoReport,
)

runner = CliRunner()


class FakeResearch:
    def __init__(self, channel: Channel, videos: list[Video]) -> None:
        self.channel_value = channel
        self.video_values = videos
        self.api = type("FakeAPI", (), {"request_counts": {"search": 1}})()
        self.video_calls: list[tuple[str, VideoQuery, str, bool]] = []

    def channel(self, reference: str, *, refresh: bool = False) -> ChannelReport:
        return ChannelReport(
            channel=self.channel_value,
            query={"reference": reference, "refresh": refresh},
            meta=ReportMeta(requests={"channels": 1}),
        )

    def search_channels(self, query: str, *, limit: int = 10) -> list[ChannelCandidate]:
        return [
            ChannelCandidate(
                channel_id=self.channel_value.channel_id,
                title=f"{query} Candidate",
                handle=self.channel_value.handle,
                url=self.channel_value.url,
            )
        ][:limit]

    def videos(
        self,
        reference: str,
        query: VideoQuery,
        *,
        command: str = "videos.list",
        refresh: bool = False,
    ) -> VideoReport:
        self.video_calls.append((reference, query, command, refresh))
        returned = self.video_values[: query.limit] if query.limit else self.video_values
        return VideoReport(
            command=command,
            channel=self.channel_value,
            query=query,
            items=returned,
            meta=ReportMeta(matched=len(self.video_values), returned=len(returned)),
        )


@pytest.fixture
def fake_research(
    monkeypatch: pytest.MonkeyPatch,
    synthetic_channel: Channel,
    synthetic_videos: list[Video],
) -> FakeResearch:
    fake = FakeResearch(synthetic_channel, synthetic_videos)
    monkeypatch.setattr(cli, "_research", lambda: fake)
    return fake


def payload(result: Any) -> dict[str, Any]:
    assert result.exit_code == 0, result.output
    return cast(dict[str, Any], json.loads(result.stdout))


def test_root_help_lists_public_command_groups() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert "auth" in result.stdout
    assert "channel" in result.stdout
    assert "videos" in result.stdout


def test_root_version_reports_package_version() -> None:
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == f"yt-research {__version__}\n"


def test_channel_info_json_and_refresh(fake_research: FakeResearch) -> None:
    result = runner.invoke(
        cli.app,
        ["channel", "info", "@exampleobservatory", "--refresh", "--format", "json"],
    )
    data = payload(result)

    assert data["schema_version"] == 1
    assert data["channel"]["channel_id"] == fake_research.channel_value.channel_id
    assert data["query"]["refresh"] is True


def test_channel_search_returns_candidates_not_a_selected_channel(
    fake_research: FakeResearch,
) -> None:
    result = runner.invoke(
        cli.app,
        ["channel", "search", "Fictional Astronomy", "--limit", "3", "--format", "json"],
    )
    data = payload(result)

    assert data["command"] == "channel.search"
    assert data["channel"] is None
    assert data["items"][0]["title"] == "Fictional Astronomy Candidate"


@pytest.mark.parametrize(
    ("command", "expected_sort", "expected_limit"),
    [
        ("latest", "published-desc", 20),
        ("top", "views", 10),
        ("first", "published-asc", 1),
    ],
)
def test_video_convenience_commands_apply_defaults(
    fake_research: FakeResearch,
    command: str,
    expected_sort: str,
    expected_limit: int,
) -> None:
    result = runner.invoke(
        cli.app,
        ["videos", command, "@exampleobservatory", "--format", "json"],
    )

    payload(result)
    _, query, report_command, _ = fake_research.video_calls[-1]
    assert query.sort.value == expected_sort
    assert query.limit == expected_limit
    assert report_command == f"videos.{command}"


def test_video_convenience_commands_accept_sort_and_limit_overrides(
    fake_research: FakeResearch,
) -> None:
    result = runner.invoke(
        cli.app,
        [
            "videos",
            "first",
            "@exampleobservatory",
            "--sort",
            "likes",
            "--limit",
            "2",
            "--format",
            "json",
        ],
    )

    payload(result)
    _, query, _, _ = fake_research.video_calls[-1]
    assert query.sort.value == "likes"
    assert query.limit == 2


def test_video_list_passes_filters_and_refresh(fake_research: FakeResearch) -> None:
    result = runner.invoke(
        cli.app,
        [
            "videos",
            "list",
            "@exampleobservatory",
            "--match",
            "tutorial",
            "--from",
            "2025-01-01",
            "--to",
            "2026-12-31",
            "--sort",
            "likes",
            "--limit",
            "1",
            "--refresh",
            "--format",
            "json",
        ],
    )

    payload(result)
    reference, query, _, refresh = fake_research.video_calls[-1]
    assert reference == "@exampleobservatory"
    assert query.match_text == "tutorial"
    assert query.date_from is not None
    assert query.date_to is not None
    assert query.sort.value == "likes"
    assert query.limit == 1
    assert refresh is True


def test_conflicting_date_options_exit_two(fake_research: FakeResearch) -> None:
    result = runner.invoke(
        cli.app,
        [
            "videos",
            "list",
            "@exampleobservatory",
            "--year",
            "2025",
            "--from",
            "2025-01-01",
        ],
    )

    assert result.exit_code == 2
    assert "year cannot be combined" in result.stderr


def test_output_file_contains_only_requested_format(
    tmp_path: Path, fake_research: FakeResearch
) -> None:
    destination = tmp_path / "result.csv"

    result = runner.invoke(
        cli.app,
        [
            "videos",
            "list",
            "@exampleobservatory",
            "--format",
            "csv",
            "--output",
            str(destination),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert destination.read_text(encoding="utf-8").startswith("video_id,title,url")


def test_domain_error_uses_stable_exit_code(
    monkeypatch: pytest.MonkeyPatch, fake_research: FakeResearch
) -> None:
    def missing(*_: object, **__: object) -> ChannelReport:
        raise NotFoundError("synthetic channel not found")

    monkeypatch.setattr(fake_research, "channel", missing)

    result = runner.invoke(cli.app, ["channel", "info", "@missing"])

    assert result.exit_code == 4
    assert "synthetic channel not found" in result.stderr


def test_warnings_use_stderr_without_corrupting_json(
    monkeypatch: pytest.MonkeyPatch, fake_research: FakeResearch
) -> None:
    original = fake_research.videos

    def videos_with_warning(*args: Any, **kwargs: Any) -> VideoReport:
        report = original(*args, **kwargs)
        report.meta.warnings.append("synthetic statistic unavailable")
        return report

    monkeypatch.setattr(fake_research, "videos", videos_with_warning)

    result = runner.invoke(
        cli.app,
        ["videos", "list", "@exampleobservatory", "--format", "json"],
    )

    data = payload(result)
    assert data["meta"]["warnings"] == ["synthetic statistic unavailable"]
    assert "Warning: synthetic statistic unavailable" in result.stderr


def test_auth_status_never_prints_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "credential_source", lambda: "environment")

    result = runner.invoke(cli.app, ["auth", "status"])

    assert result.exit_code == 0
    assert "YT_RESEARCH_API_KEY" in result.stdout
    assert "secret" not in result.stdout.casefold()
