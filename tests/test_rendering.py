from __future__ import annotations

import csv
import io
import json
from typing import Any

from yt_research.models import (
    AnalysisQuery,
    AnalysisReport,
    AnalysisSummary,
    Channel,
    ReportMeta,
    Video,
    VideoQuery,
    VideoReport,
)
from yt_research.rendering import CSV_COLUMNS, OutputFormat, render, render_csv, render_json


def make_report(channel: Channel, videos: list[Video]) -> VideoReport:
    return VideoReport(
        command="videos.list",
        channel=channel,
        query=VideoQuery(),
        items=videos,
        meta=ReportMeta(matched=len(videos), returned=len(videos), warnings=["synthetic warning"]),
    )


def make_analysis_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "command": "channel.analyze",
        "fetched_at": "2026-09-03T12:00:00Z",
        "channel": {"title": "Example Observatory", "handle": "@exampleobservatory"},
        "query": {
            "match_text": "telescope",
            "date_from": "2025-09-03",
            "date_to": "2026-09-03",
            "limit": 10,
        },
        "summary": {
            "video_count": 2,
            "published_from": "2025-10-03",
            "published_to": "2026-09-02",
            "total_views": 350,
            "median_views": 175,
            "median_likes": 15,
            "median_comments": 2,
            "median_duration_seconds": 90,
            "like_rate": 0.125,
            "comment_rate": 0.02,
            "uploads_per_month": 0.17,
            "median_days_between_uploads": 14,
            "coverage": {
                "views": 2,
                "likes": 1,
                "comments": 2,
                "duration": 2,
                "like_rate": 1,
                "comment_rate": 2,
            },
        },
        "monthly_cohorts": [
            {
                "month": "2026-02",
                "video_count": 2,
                "total_views": 350,
                "median_views": 175,
                "like_rate": 0.125,
                "comment_rate": 0.02,
                "median_duration_seconds": 90,
            }
        ],
        "items": [
            {
                "video_id": "video-a",
                "title": "Café & Telescope",
                "url": "https://www.youtube.com/watch?v=video-a",
                "published_at": "2026-02-03T11:00:00Z",
                "views": 250,
                "year_median_views": 100,
                "year_cohort_size": 4,
                "view_multiplier": 2.5,
            }
        ],
        "meta": {"matched": 2, "returned": 1, "warnings": [], "scanned_all": True},
    }


def test_json_is_parseable_and_preserves_unicode_and_nulls(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    payload = json.loads(render_json(make_report(synthetic_channel, synthetic_videos)))

    assert payload["schema_version"] == 1
    assert payload["items"][0]["title"] == "Caf\u00e9 & Telescope"
    assert payload["items"][1]["likes"] is None
    assert payload["meta"]["warnings"] == ["synthetic warning"]


def test_csv_has_fixed_columns_and_blank_missing_statistics(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    content = render_csv(make_report(synthetic_channel, synthetic_videos))
    rows = list(csv.DictReader(io.StringIO(content)))

    assert tuple(rows[0]) == CSV_COLUMNS
    assert rows[1]["likes"] == ""
    assert rows[1]["comments"] == ""


def test_plain_table_contains_video_values_without_color(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    output = render(
        make_report(synthetic_channel, synthetic_videos), OutputFormat.table, no_color=True
    )

    assert "Synthetic Tutorial" in output
    assert "250" in output
    assert "\x1b[" not in output


def test_table_formats_large_count_values_with_grouping_separators(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    videos = [synthetic_videos[0].model_copy(update={"views": 1_234_567, "likes": 12_345})]
    video_table = render(make_report(synthetic_channel, videos), OutputFormat.table, no_color=True)
    channel_table = render(
        {
            "channel": synthetic_channel.model_copy(
                update={"subscribers": 21_200_000, "views": 556_234_269}
            )
        },
        OutputFormat.table,
        no_color=True,
    )

    assert "1,234,567" in video_table
    assert "12,345" in video_table
    assert "21,200,000" in channel_table
    assert "556,234,269" in channel_table


def test_render_json_ends_with_single_newline(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    output = render(make_report(synthetic_channel, synthetic_videos), OutputFormat.json)

    assert output.endswith("\n")
    assert not output.endswith("\n\n")


def test_analysis_table_has_context_and_separate_sections() -> None:
    output = render(make_analysis_report(), OutputFormat.table, no_color=True)

    assert "Channel: Example Observatory (@exampleobservatory)" in output
    assert "Window: 2025-09-03 to 2026-09-03 UTC" in output
    assert "Summary" in output
    assert "Monthly publication cohorts" in output
    assert "Breakout videos" in output
    assert "Current snapshot metrics grouped by publish month" in output
    assert "not historical growth" in output
    assert "12.50%" in output
    assert "2.50x" in output
    assert "Café & Telescope" in output
    assert "\x1b[" not in output


def test_analysis_json_keeps_numeric_contract_values() -> None:
    payload = json.loads(render(make_analysis_report(), OutputFormat.json))

    assert payload["command"] == "channel.analyze"
    assert payload["summary"]["like_rate"] == 0.125
    assert payload["monthly_cohorts"][0]["month"] == "2026-02"
    assert payload["items"][0]["view_multiplier"] == 2.5


def test_analysis_table_labels_an_unbounded_query_as_all_history() -> None:
    report = make_analysis_report()
    report["query"] = {
        "match_text": None,
        "date_from": None,
        "date_to": None,
        "limit": 10,
    }

    output = render(report, OutputFormat.table, no_color=True)

    assert "Window: All history" in output


def test_typed_analysis_report_renders_effective_query_contract(
    synthetic_channel: Channel,
) -> None:
    report = AnalysisReport(
        channel=synthetic_channel,
        query=AnalysisQuery.model_validate(
            {
                "match": "telescope",
                "from": "2025-09-03",
                "to": "2026-09-03",
            }
        ),
        summary=AnalysisSummary(),
    )

    table = render(report, OutputFormat.table, no_color=True)
    payload = json.loads(render(report, OutputFormat.json))

    assert "Window: 2025-09-03 to 2026-09-03 UTC" in table
    assert payload["query"] == {
        "match_text": "telescope",
        "date_from": "2025-09-03",
        "date_to": "2026-09-03",
        "limit": 10,
    }
