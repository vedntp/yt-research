"""Render research results without mixing diagnostics into stdout."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

CSV_COLUMNS = (
    "video_id",
    "title",
    "url",
    "published_at",
    "duration_seconds",
    "views",
    "likes",
    "comments",
)


class OutputFormat(StrEnum):
    table = "table"
    json = "json"
    csv = "csv"


def as_data(value: Any) -> Any:
    """Convert Pydantic models and nested values into JSON-ready data."""

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {key: as_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_data(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, Mapping):
        raw_items = data.get("items", [])
    elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
        raw_items = data
    else:
        raw_items = []
    return [dict(item) for item in raw_items if isinstance(item, Mapping)]


def render_json(value: Any) -> str:
    return json.dumps(as_data(value), ensure_ascii=False, indent=2) + "\n"


def render_csv(value: Any) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for item in _items(as_data(value)):
        writer.writerow(
            {column: "" if item.get(column) is None else item.get(column) for column in CSV_COLUMNS}
        )
    return output.getvalue()


def _display(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _number(value: Any, *, decimals: int = 2) -> str:
    """Format a report number without making tables needlessly noisy."""

    if value is None:
        return "-"
    if isinstance(value, bool):
        return _display(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
    return _display(value)


def _percentage(value: Any) -> str:
    """Render a ratio as a percentage while preserving unavailable values."""

    if value is None:
        return "-"
    if isinstance(value, bool):
        return _display(value)
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return _display(value)


def _multiplier(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return f"{_display(value)}x"


def _duration(value: Any) -> str:
    """Format duration seconds compactly, retaining seconds for short values."""

    if value is None:
        return "-"
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return _display(value)
    seconds = int(value)
    if seconds < 60:
        return f"{_number(value)}s"
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m {remainder}s"


def _mapping_value(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _analysis_window(data: Mapping[str, Any]) -> str:
    """Describe an analysis query in terms useful to a terminal reader."""

    raw_query = data.get("query", {})
    query = raw_query if isinstance(raw_query, Mapping) else {}
    raw_window = query.get("window")
    window = raw_window if isinstance(raw_window, Mapping) else query

    if _mapping_value(window, "all", "all_history") is True:
        return "All history"

    months = _mapping_value(window, "months", "month_count")
    if months is not None:
        return f"Last {_number(months)} calendar months"

    year = _mapping_value(window, "year")
    if year is not None:
        return f"Calendar year {_display(year)}"

    date_from = _mapping_value(
        window,
        "from",
        "date_from",
        "effective_from",
        "published_from",
    )
    date_to = _mapping_value(window, "to", "date_to", "effective_to", "published_to")
    if date_from is not None or date_to is not None:
        return f"{_display(date_from)} to {_display(date_to)} UTC"
    if "date_from" in window and "date_to" in window:
        return "All history"

    summary = data.get("summary")
    if isinstance(summary, Mapping):
        date_from = summary.get("published_from")
        date_to = summary.get("published_to")
        if date_from is not None or date_to is not None:
            return f"{_display(date_from)} to {_display(date_to)} UTC"
    return "Default: latest 12 calendar months"


def _format_coverage(value: Any) -> str:
    if value is None:
        return "-"
    if not isinstance(value, Mapping):
        return _number(value)
    parts: list[str] = []
    for key, item in value.items():
        label = str(key).replace("_", " ")
        if isinstance(item, Mapping):
            available = _mapping_value(item, "available", "count", "present")
            total = _mapping_value(item, "total", "video_count", "denominator")
            if available is not None and total is not None:
                item_text = f"{_number(available)}/{_number(total)}"
            else:
                item_text = _format_coverage(item)
        else:
            item_text = _number(item)
        parts.append(f"{label}: {item_text}")
    return "; ".join(parts) or "-"


def _analysis_summary_rows(summary: Mapping[str, Any]) -> list[tuple[str, str]]:
    labels = (
        ("video_count", "Videos"),
        ("published_from", "Published from"),
        ("published_to", "Published to"),
        ("total_views", "Total views"),
        ("median_views", "Median views"),
        ("median_likes", "Median likes"),
        ("median_comments", "Median comments"),
        ("median_duration_seconds", "Median duration"),
        ("like_rate", "Like rate"),
        ("comment_rate", "Comment rate"),
        ("uploads_per_month", "Uploads per month"),
        ("median_days_between_uploads", "Median days between uploads"),
        ("coverage", "Metric coverage"),
    )
    rows: list[tuple[str, str]] = []
    for key, label in labels:
        value = summary.get(key)
        if key in {"like_rate", "comment_rate"}:
            rendered = _percentage(value)
        elif key == "median_duration_seconds":
            rendered = _duration(value)
        elif key == "coverage":
            rendered = _format_coverage(value)
        else:
            rendered = _number(value)

        rows.append((label, rendered))
    return rows


def _analysis_context(console: Console, data: Mapping[str, Any]) -> None:
    channel = data.get("channel")
    if isinstance(channel, Mapping):
        title = channel.get("title")
        handle = channel.get("handle") or channel.get("custom_url")
        identity = _display(title)
        if handle:
            identity = f"{identity} ({_display(handle)})"
        console.print(f"Channel: {identity}")
    else:
        console.print("Channel: -")
    console.print(f"Window: {_analysis_window(data)}")


def _render_analysis_table(data: Mapping[str, Any], console: Console) -> None:
    """Render the multi-section channel analysis report.

    Analysis reports intentionally have their own renderer: unlike a video list,
    their rows contain summary and cohort data in addition to video records.
    """

    _analysis_context(console, data)

    summary_value = data.get("summary")
    summary = summary_value if isinstance(summary_value, Mapping) else {}
    console.print("\nSummary")
    summary_table = Table("Metric", "Value", show_lines=False)
    for label, value in _analysis_summary_rows(summary):
        summary_table.add_row(label, value)
    console.print(summary_table)

    console.print("\nMonthly publication cohorts")
    console.print(
        "Current snapshot metrics grouped by publish month; these are not historical growth."
    )
    monthly_value = data.get("monthly_cohorts", [])
    if isinstance(monthly_value, Sequence) and not isinstance(monthly_value, (str, bytes)):
        monthly = [dict(item) for item in monthly_value if isinstance(item, Mapping)]
    else:
        monthly = []
    monthly_table = Table(
        "Month",
        "Videos",
        "Total views",
        "Median views",
        "Like rate",
        "Comment rate",
        "Median duration",
        show_lines=False,
    )
    for row in monthly:
        monthly_table.add_row(
            _display(_mapping_value(row, "month", "publication_month")),
            _number(row.get("video_count")),
            _number(row.get("total_views")),
            _number(row.get("median_views")),
            _percentage(row.get("like_rate")),
            _percentage(row.get("comment_rate")),
            _duration(row.get("median_duration_seconds")),
        )
    if monthly:
        console.print(monthly_table)
    else:
        console.print("No matching publication months.")

    console.print("\nBreakout videos")
    items = _items(data)
    breakout_table = Table(
        "Published",
        "Title",
        "Views",
        "Year median",
        "Cohort",
        "View multiplier",
        "URL",
        show_lines=False,
    )
    for item in items:
        breakout_table.add_row(
            _display(item.get("published_at")),
            _display(item.get("title")),
            _number(item.get("views")),
            _number(item.get("year_median_views")),
            _number(item.get("year_cohort_size")),
            _multiplier(item.get("view_multiplier")),
            _display(item.get("url")),
        )
    if items:
        console.print(breakout_table)
    else:
        console.print("No breakout videos with a comparable publication-year cohort.")


def render_table(value: Any, *, no_color: bool = False) -> str:
    data = as_data(value)
    output = io.StringIO()
    console = Console(
        file=output,
        force_terminal=not no_color,
        color_system=None if no_color else "auto",
        width=120,
    )
    if isinstance(data, Mapping) and data.get("command") == "channel.analyze":
        _render_analysis_table(data, console)
        return output.getvalue()

    items = _items(data)
    if items:
        is_video_report = any("video_id" in item for item in items)
        columns = (
            ("Published", "Title", "Views", "Likes", "URL")
            if is_video_report
            else ("Title", "Handle", "Channel ID", "Subscribers")
        )
        table = Table(*columns, show_lines=False)
        for item in items:
            if is_video_report:
                table.add_row(
                    _display(item.get("published_at")),
                    _display(item.get("title")),
                    _display(item.get("views")),
                    _display(item.get("likes")),
                    _display(item.get("url")),
                )
            else:
                table.add_row(
                    _display(item.get("title")),
                    _display(item.get("handle") or item.get("custom_url")),
                    _display(item.get("channel_id")),
                    _display(item.get("subscribers")),
                )
        console.print(table)
    elif isinstance(data, Mapping) and data.get("channel") is not None:
        # A channel info response is a single record. Hide report bookkeeping.
        record = data.get("channel", data)
        if isinstance(record, Mapping):
            table = Table("Field", "Value", show_header=False)
            for key, item in record.items():
                if isinstance(item, (Mapping, list)):
                    continue
                table.add_row(str(key).replace("_", " ").title(), _display(item))
            console.print(table)
        else:
            console.print("No results.")
    else:
        console.print("No results.")
    return output.getvalue()


def render(value: Any, output_format: OutputFormat, *, no_color: bool = False) -> str:
    if output_format is OutputFormat.json:
        return render_json(value)
    if output_format is OutputFormat.csv:
        return render_csv(value)
    return render_table(value, no_color=no_color)


def write_rendered(content: str, output: Path | None) -> None:
    """Write rendered content either to a file or stdout."""

    if output is None:
        import sys

        sys.stdout.write(content)
        sys.stdout.flush()
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="")
