from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
from typer.testing import CliRunner

import yt_research.cli as cli
from yt_research import __version__
from yt_research.errors import NotFoundError
from yt_research.models import (
    AnalysisQuery,
    AnalysisReport,
    AnalysisSummary,
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
        self.analysis_calls: list[tuple[str, AnalysisQuery, bool]] = []

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

    def analyze(
        self, reference: str, query: AnalysisQuery, *, refresh: bool = False
    ) -> AnalysisReport:
        self.analysis_calls.append((reference, query, refresh))
        return AnalysisReport(
            channel=self.channel_value,
            query=query,
            summary=AnalysisSummary(),
            meta=ReportMeta(),
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


@pytest.mark.parametrize(
    "channel_ref",
    [
        "UC000000000000000000001",
        "@exampleobservatory",
        "https://www.youtube.com/@exampleobservatory",
    ],
)
def test_root_channel_reference_runs_default_analysis(
    fake_research: FakeResearch, channel_ref: str
) -> None:
    result = runner.invoke(cli.app, [channel_ref, "--format", "json"])

    data = payload(result)
    reference, query, refresh = fake_research.analysis_calls[-1]
    assert data["command"] == "channel.analyze"
    assert reference == channel_ref
    assert query.date_from is not None
    assert query.date_to is not None
    assert query.limit == 10
    assert refresh is False


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


def test_channel_analyze_defaults_to_twelve_months_and_clamps_leap_day(
    monkeypatch: pytest.MonkeyPatch, fake_research: FakeResearch
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> FrozenDateTime:
            return cls(2024, 2, 29, 12, tzinfo=tz)

    monkeypatch.setattr(cli, "datetime", FrozenDateTime)

    result = runner.invoke(
        cli.app, ["channel", "analyze", "@exampleobservatory", "--format", "json"]
    )

    payload(result)
    reference, query, refresh = fake_research.analysis_calls[-1]
    assert reference == "@exampleobservatory"
    assert query.date_from.isoformat() == "2023-02-28"
    assert query.date_to.isoformat() == "2024-02-29"
    assert query.limit == 10
    assert refresh is False


def test_channel_analyze_passes_window_filters_and_refresh(
    fake_research: FakeResearch,
) -> None:
    result = runner.invoke(
        cli.app,
        [
            "channel",
            "analyze",
            "@exampleobservatory",
            "--from",
            "2025-01-01",
            "--to",
            "2025-12-31",
            "--match",
            "tutorial",
            "--limit",
            "4",
            "--refresh",
            "--format",
            "json",
        ],
    )

    payload(result)
    _, query, refresh = fake_research.analysis_calls[-1]
    assert query.match_text == "tutorial"
    assert query.date_from.isoformat() == "2025-01-01"
    assert query.date_to.isoformat() == "2025-12-31"
    assert query.limit == 4
    assert refresh is True


def test_channel_analyze_all_history_leaves_both_bounds_open(
    fake_research: FakeResearch,
) -> None:
    result = runner.invoke(
        cli.app,
        ["channel", "analyze", "@exampleobservatory", "--all", "--format", "json"],
    )

    payload(result)
    _, query, _ = fake_research.analysis_calls[-1]
    assert query.date_from is None
    assert query.date_to is None


@pytest.mark.parametrize(
    ("window_args", "expected_from", "expected_to"),
    [
        (["--months", "3"], "2026-06-03", "2026-09-03"),
        (["--year", "2025"], "2025-01-01", "2025-12-31"),
        (["--to", "2025-06-30"], None, "2025-06-30"),
        (["--from", "2026-01-01"], "2026-01-01", "2026-09-03"),
    ],
)
def test_channel_analyze_resolves_each_custom_window_style(
    monkeypatch: pytest.MonkeyPatch,
    fake_research: FakeResearch,
    window_args: list[str],
    expected_from: str | None,
    expected_to: str,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> FrozenDateTime:
            return cls(2026, 9, 3, 12, tzinfo=tz)

    monkeypatch.setattr(cli, "datetime", FrozenDateTime)

    result = runner.invoke(
        cli.app,
        ["channel", "analyze", "@exampleobservatory", *window_args, "--format", "json"],
    )

    payload(result)
    _, query, _ = fake_research.analysis_calls[-1]
    actual_from = query.date_from.isoformat() if query.date_from else None
    assert actual_from == expected_from
    assert query.date_to is not None
    assert query.date_to.isoformat() == expected_to


def test_channel_analyze_rejects_malformed_dates(fake_research: FakeResearch) -> None:
    result = runner.invoke(
        cli.app,
        ["channel", "analyze", "@exampleobservatory", "--from", "06/01/2025"],
    )

    assert result.exit_code == 2
    assert "dates must use YYYY-MM-DD format" in result.stderr
    assert not fake_research.analysis_calls


def test_channel_analyze_rejects_conflicting_window_styles(
    fake_research: FakeResearch,
) -> None:
    result = runner.invoke(
        cli.app,
        [
            "channel",
            "analyze",
            "@exampleobservatory",
            "--months",
            "3",
            "--year",
            "2025",
        ],
    )

    assert result.exit_code == 2
    assert "--months cannot be combined with --year" in result.stderr
    assert not fake_research.analysis_calls


def test_channel_analyze_rejects_csv_output(
    fake_research: FakeResearch,
) -> None:
    result = runner.invoke(
        cli.app,
        ["channel", "analyze", "@exampleobservatory", "--format", "csv"],
    )

    assert result.exit_code == 2
    assert "Invalid value" in result.stderr
    assert "table" in result.stderr
    assert "json" in result.stderr
    assert not fake_research.analysis_calls


def test_channel_analyze_output_file_defaults_to_json(
    tmp_path: Path, fake_research: FakeResearch
) -> None:
    destination = tmp_path / "analysis.out"

    result = runner.invoke(
        cli.app,
        ["channel", "analyze", "@exampleobservatory", "--output", str(destination)],
    )

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    data = json.loads(destination.read_text(encoding="utf-8"))
    assert data["command"] == "channel.analyze"
    assert "summary" in data
    assert "monthly_cohorts" in data


def test_channel_analyze_table_renders_the_typed_report(
    fake_research: FakeResearch,
) -> None:
    result = runner.invoke(
        cli.app,
        ["channel", "analyze", "@exampleobservatory", "--format", "table", "--no-color"],
    )

    assert result.exit_code == 0, result.output
    assert "Summary" in result.stdout
    assert "Monthly publication cohorts" in result.stdout
    assert "Breakout videos" in result.stdout


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


def test_video_list_defaults_to_ten_newest_uploads(fake_research: FakeResearch) -> None:
    result = runner.invoke(
        cli.app,
        ["videos", "list", "@exampleobservatory", "--format", "json"],
    )

    payload(result)
    _, query, report_command, _ = fake_research.video_calls[-1]
    assert query.sort.value == "published-desc"
    assert query.limit == 10
    assert report_command == "videos.list"


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
