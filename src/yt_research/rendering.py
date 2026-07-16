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


def render_table(value: Any, *, no_color: bool = False) -> str:
    data = as_data(value)
    output = io.StringIO()
    console = Console(
        file=output,
        force_terminal=not no_color,
        color_system=None if no_color else "auto",
        width=120,
    )
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
