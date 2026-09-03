"""Command-line interface for public YouTube channel research."""

# Typer declares CLI metadata through function-call defaults by design.
# ruff: noqa: B008

from __future__ import annotations

import calendar
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from . import __version__
from .cache import ChannelCache
from .credentials import (
    CredentialError,
    credential_source,
    delete_api_key,
    get_api_key,
    store_api_key,
)
from .errors import InvalidInputError, YTResearchError
from .models import AnalysisQuery, ReportMeta, SortOrder, VideoQuery
from .rendering import OutputFormat, as_data, render, write_rendered
from .research import Research
from .youtube import YouTubeClient

app = typer.Typer(
    name="yt-research",
    help="Research public YouTube channels and upload histories.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)
auth_app = typer.Typer(help="Manage the YouTube Data API key.", no_args_is_help=True)
channel_app = typer.Typer(help="Inspect and discover public channels.", no_args_is_help=True)
videos_app = typer.Typer(help="Research videos published by a channel.", no_args_is_help=True)
app.add_typer(auth_app, name="auth")
app.add_typer(channel_app, name="channel")
app.add_typer(videos_app, name="videos")


class _AnalysisOutputFormat(StrEnum):
    table = "table"
    json = "json"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"yt-research {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Research public YouTube channels and upload histories."""


def _fail(message: str, exit_code: int) -> None:
    typer.echo(f"Error: {message}", err=True)
    raise typer.Exit(exit_code)


def _run(operation: Callable[[], Any]) -> Any:
    try:
        return operation()
    except CredentialError as exc:
        _fail(str(exc), 3)
    except ValidationError as exc:
        message = "; ".join(error["msg"] for error in exc.errors())
        _fail(message, 2)
    except YTResearchError as exc:
        _fail(str(exc), exc.exit_code)
    except OSError as exc:
        _fail(str(exc), 5)


def _research() -> Research:
    return Research(YouTubeClient(get_api_key()), ChannelCache())


def _with_research(operation: Callable[[Research], Any]) -> Any:
    research = _research()
    try:
        return operation(research)
    finally:
        close = getattr(research.api, "close", None)
        if callable(close):
            close()


def _selected_format(value: OutputFormat | None, output: Path | None = None) -> OutputFormat:
    if value is not None:
        return value
    if output is not None:
        return OutputFormat.json
    return OutputFormat.table if sys.stdout.isatty() else OutputFormat.json


def _emit(
    value: Any,
    *,
    output_format: OutputFormat | None,
    output: Path | None,
    no_color: bool,
) -> None:
    selected = _selected_format(output_format, output)
    try:
        write_rendered(render(value, selected, no_color=no_color), output)
    except OSError as exc:
        _fail(f"Could not write output: {exc}", 5)
    data = as_data(value)
    if isinstance(data, dict):
        meta = data.get("meta")
        if isinstance(meta, dict):
            for warning in meta.get("warnings", []):
                typer.echo(f"Warning: {warning}", err=True)


@auth_app.command("set")
def auth_set() -> None:
    """Save an API key in the operating system secret store."""

    api_key = typer.prompt("YouTube Data API key", hide_input=True, confirmation_prompt=True)
    _run(lambda: store_api_key(api_key))
    typer.echo("API key stored in the system secret store.")


@auth_app.command("status")
def auth_status() -> None:
    """Show whether a key is configured without revealing it."""

    source = _run(credential_source)
    if source == "environment":
        typer.echo("API key configured through YT_RESEARCH_API_KEY.")
    elif source == "keyring":
        typer.echo("API key configured in the system secret store.")
    else:
        typer.echo("No API key configured.")


@auth_app.command("delete")
def auth_delete() -> None:
    """Delete the API key from the operating system secret store."""

    deleted = _run(delete_api_key)
    typer.echo("Stored API key deleted." if deleted else "No stored API key found.")


@channel_app.command("info")
def channel_info(
    channel_ref: str = typer.Argument(..., help="Channel ID, @handle, or channel URL."),
    output_format: OutputFormat | None = typer.Option(None, "--format", help="Output format."),
    output: Path | None = typer.Option(
        None, "--output", dir_okay=False, help="Write output to this file."
    ),
    refresh: bool = typer.Option(False, "--refresh", help="Bypass cached channel identity."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable terminal color."),
) -> None:
    """Show metadata for one public channel."""

    report = _run(
        lambda: _with_research(lambda research: research.channel(channel_ref, refresh=refresh))
    )
    _emit(report, output_format=output_format, output=output, no_color=no_color)


@channel_app.command("search")
def channel_search(
    query: str = typer.Argument(..., help="Channel name to search for."),
    limit: int = typer.Option(10, "--limit", min=1, max=50, help="Maximum candidates."),
    output_format: OutputFormat | None = typer.Option(None, "--format", help="Output format."),
    output: Path | None = typer.Option(
        None, "--output", dir_okay=False, help="Write output to this file."
    ),
    no_color: bool = typer.Option(False, "--no-color", help="Disable terminal color."),
) -> None:
    """Return candidates for an ambiguous channel name."""

    def search() -> Any:
        def perform(research: Research) -> dict[str, Any]:
            items = research.search_channels(query, limit=limit)
            requests = getattr(research.api, "request_counts", {})
            return {
                "schema_version": 1,
                "command": "channel.search",
                "fetched_at": datetime.now(UTC).isoformat(),
                "channel": None,
                "query": {"text": query, "limit": limit},
                "items": items,
                "meta": ReportMeta(
                    matched=len(items),
                    returned=len(items),
                    requests=dict(requests),
                ),
            }

        return _with_research(perform)

    report = _run(search)
    _emit(report, output_format=output_format, output=output, no_color=no_color)


def _video_report(
    command: str,
    channel_ref: str,
    *,
    match_text: str | None,
    year: int | None,
    date_from: str | None,
    date_to: str | None,
    sort: SortOrder,
    limit: int | None,
    output_format: OutputFormat | None,
    output: Path | None,
    refresh: bool,
    no_color: bool,
) -> None:
    def research_videos() -> Any:
        try:
            parsed_from = date.fromisoformat(date_from) if date_from else None
            parsed_to = date.fromisoformat(date_to) if date_to else None
        except ValueError as exc:
            raise InvalidInputError("dates must use YYYY-MM-DD format") from exc
        query = VideoQuery.model_validate(
            {
                "match_text": match_text,
                "year": year,
                "date_from": parsed_from,
                "date_to": parsed_to,
                "sort": sort,
                "limit": limit,
            }
        )
        return _with_research(
            lambda research: research.videos(channel_ref, query, command=command, refresh=refresh)
        )

    report = _run(research_videos)
    _emit(report, output_format=output_format, output=output, no_color=no_color)


def _validate_limit(limit: int | None) -> int | None:
    if limit is not None and limit < 1:
        _fail("--limit must be at least 1.", 2)
    return limit


def _subtract_calendar_months(value: date, months: int) -> date:
    """Subtract calendar months while clamping the day to the target month.

    A calendar-month window should preserve the day where possible (for example,
    September 3 minus twelve months is September 3 of the prior year), but a
    date such as February 29 may not exist in the target month/year.  In that
    case use the final valid day of the target month.
    """

    month_index = value.year * 12 + value.month - 1 - months
    target_year, target_month_index = divmod(month_index, 12)
    target_month = target_month_index + 1
    if target_year < date.min.year or target_year > date.max.year:
        raise InvalidInputError("--months value is outside the supported date range")
    target_day = min(value.day, calendar.monthrange(target_year, target_month)[1])
    return date(target_year, target_month, target_day)


def _analysis_window(
    *,
    months: int | None,
    all_history: bool,
    year: int | None,
    date_from: str | None,
    date_to: str | None,
) -> tuple[date | None, date | None]:
    """Resolve analysis window options into inclusive date boundaries."""

    has_range = date_from is not None or date_to is not None
    if months is not None and all_history:
        raise InvalidInputError("--months cannot be combined with --all")
    if months is not None and year is not None:
        raise InvalidInputError("--months cannot be combined with --year")
    if months is not None and has_range:
        raise InvalidInputError("--months cannot be combined with --from or --to")
    if all_history and year is not None:
        raise InvalidInputError("--all cannot be combined with --year")
    if all_history and has_range:
        raise InvalidInputError("--all cannot be combined with --from or --to")
    if year is not None and has_range:
        raise InvalidInputError("--year cannot be combined with --from or --to")

    today = datetime.now(UTC).date()
    if all_history:
        return None, None
    if year is not None:
        return date(year, 1, 1), date(year, 12, 31)
    if months is not None or not has_range:
        count = 12 if months is None else months
        return _subtract_calendar_months(today, count), today

    try:
        parsed_from = date.fromisoformat(date_from) if date_from else None
        parsed_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise InvalidInputError("dates must use YYYY-MM-DD format") from exc
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise InvalidInputError("from cannot be later than to")
    return parsed_from, parsed_to if parsed_to is not None else today


@channel_app.command("analyze")
def channel_analyze(
    channel_ref: str = typer.Argument(..., help="Channel ID, @handle, or channel URL."),
    months: int | None = typer.Option(
        None, "--months", min=1, help="Analyze this many calendar months ending today."
    ),
    all_history: bool = typer.Option(False, "--all", help="Analyze the complete upload history."),
    year: int | None = typer.Option(
        None, "--year", min=1970, max=9999, help="Analyze one calendar year."
    ),
    date_from: str | None = typer.Option(None, "--from", metavar="YYYY-MM-DD"),
    date_to: str | None = typer.Option(None, "--to", metavar="YYYY-MM-DD"),
    match_text: str | None = typer.Option(
        None, "--match", help="Case-insensitive title substring."
    ),
    limit: int = typer.Option(10, "--limit", min=1, help="Maximum breakout videos."),
    output_format: _AnalysisOutputFormat | None = typer.Option(
        None, "--format", help="Output format."
    ),
    output: Path | None = typer.Option(
        None, "--output", dir_okay=False, help="Write output to this file."
    ),
    refresh: bool = typer.Option(False, "--refresh", help="Bypass cached channel identity."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable terminal color."),
) -> None:
    """Summarize a channel's upload history and highlight breakout videos."""

    def research_analysis() -> Any:
        parsed_from, parsed_to = _analysis_window(
            months=months,
            all_history=all_history,
            year=year,
            date_from=date_from,
            date_to=date_to,
        )
        query = AnalysisQuery.model_validate(
            {
                "match_text": match_text,
                "date_from": parsed_from,
                "date_to": parsed_to,
                "limit": limit,
            }
        )
        return _with_research(
            lambda research: research.analyze(channel_ref, query, refresh=refresh)
        )

    report = _run(research_analysis)
    selected_format = OutputFormat(output_format.value) if output_format is not None else None
    _emit(report, output_format=selected_format, output=output, no_color=no_color)


@videos_app.command("list")
def videos_list(
    channel_ref: str = typer.Argument(..., help="Channel ID, @handle, or channel URL."),
    match_text: str | None = typer.Option(
        None, "--match", help="Case-insensitive title substring."
    ),
    year: int | None = typer.Option(None, "--year", min=1970, max=9999),
    date_from: str | None = typer.Option(None, "--from", metavar="YYYY-MM-DD"),
    date_to: str | None = typer.Option(None, "--to", metavar="YYYY-MM-DD"),
    sort: SortOrder = typer.Option(SortOrder.PUBLISHED_DESC, "--sort"),
    limit: int | None = typer.Option(None, "--limit", min=1),
    output_format: OutputFormat | None = typer.Option(None, "--format"),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
    refresh: bool = typer.Option(False, "--refresh"),
    no_color: bool = typer.Option(False, "--no-color"),
) -> None:
    """List all videos matching the supplied filters."""

    _video_report(
        "videos.list",
        channel_ref,
        match_text=match_text,
        year=year,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=_validate_limit(limit),
        output_format=output_format,
        output=output,
        refresh=refresh,
        no_color=no_color,
    )


@videos_app.command("latest")
def videos_latest(
    channel_ref: str = typer.Argument(..., help="Channel ID, @handle, or channel URL."),
    match_text: str | None = typer.Option(
        None, "--match", help="Case-insensitive title substring."
    ),
    year: int | None = typer.Option(None, "--year", min=1970, max=9999),
    date_from: str | None = typer.Option(None, "--from", metavar="YYYY-MM-DD"),
    date_to: str | None = typer.Option(None, "--to", metavar="YYYY-MM-DD"),
    sort: SortOrder = typer.Option(SortOrder.PUBLISHED_DESC, "--sort"),
    limit: int = typer.Option(20, "--limit", min=1),
    output_format: OutputFormat | None = typer.Option(None, "--format"),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
    refresh: bool = typer.Option(False, "--refresh"),
    no_color: bool = typer.Option(False, "--no-color"),
) -> None:
    """Show the newest matching videos."""

    _video_report(
        "videos.latest",
        channel_ref,
        match_text=match_text,
        year=year,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        output_format=output_format,
        output=output,
        refresh=refresh,
        no_color=no_color,
    )


@videos_app.command("top")
def videos_top(
    channel_ref: str = typer.Argument(..., help="Channel ID, @handle, or channel URL."),
    match_text: str | None = typer.Option(
        None, "--match", help="Case-insensitive title substring."
    ),
    year: int | None = typer.Option(None, "--year", min=1970, max=9999),
    date_from: str | None = typer.Option(None, "--from", metavar="YYYY-MM-DD"),
    date_to: str | None = typer.Option(None, "--to", metavar="YYYY-MM-DD"),
    sort: SortOrder = typer.Option(SortOrder.VIEWS, "--sort"),
    limit: int = typer.Option(10, "--limit", min=1),
    output_format: OutputFormat | None = typer.Option(None, "--format"),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
    refresh: bool = typer.Option(False, "--refresh"),
    no_color: bool = typer.Option(False, "--no-color"),
) -> None:
    """Show matching videos with the highest current view counts."""

    _video_report(
        "videos.top",
        channel_ref,
        match_text=match_text,
        year=year,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        output_format=output_format,
        output=output,
        refresh=refresh,
        no_color=no_color,
    )


@videos_app.command("first")
def videos_first(
    channel_ref: str = typer.Argument(..., help="Channel ID, @handle, or channel URL."),
    match_text: str | None = typer.Option(
        None, "--match", help="Case-insensitive title substring."
    ),
    year: int | None = typer.Option(None, "--year", min=1970, max=9999),
    date_from: str | None = typer.Option(None, "--from", metavar="YYYY-MM-DD"),
    date_to: str | None = typer.Option(None, "--to", metavar="YYYY-MM-DD"),
    sort: SortOrder = typer.Option(SortOrder.PUBLISHED_ASC, "--sort"),
    limit: int = typer.Option(1, "--limit", min=1),
    output_format: OutputFormat | None = typer.Option(None, "--format"),
    output: Path | None = typer.Option(None, "--output", dir_okay=False),
    refresh: bool = typer.Option(False, "--refresh"),
    no_color: bool = typer.Option(False, "--no-color"),
) -> None:
    """Show the oldest matching video."""

    _video_report(
        "videos.first",
        channel_ref,
        match_text=match_text,
        year=year,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        output_format=output_format,
        output=output,
        refresh=refresh,
        no_color=no_color,
    )


if __name__ == "__main__":
    app()
