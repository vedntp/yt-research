from __future__ import annotations

import csv
import io
import json

from yt_research.models import Channel, ReportMeta, Video, VideoQuery, VideoReport
from yt_research.rendering import CSV_COLUMNS, OutputFormat, render, render_csv, render_json


def make_report(channel: Channel, videos: list[Video]) -> VideoReport:
    return VideoReport(
        command="videos.list",
        channel=channel,
        query=VideoQuery(),
        items=videos,
        meta=ReportMeta(matched=len(videos), returned=len(videos), warnings=["synthetic warning"]),
    )


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


def test_render_json_ends_with_single_newline(
    synthetic_channel: Channel, synthetic_videos: list[Video]
) -> None:
    output = render(make_report(synthetic_channel, synthetic_videos), OutputFormat.json)

    assert output.endswith("\n")
    assert not output.endswith("\n\n")
