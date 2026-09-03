# Command reference

Run `yt-research COMMAND --help` for the authoritative options installed with your version.

## Authentication

- `auth set` stores an API key in the native secret store.
- `auth status` reports whether a key is available and where it came from, without displaying it.
- `auth delete` removes the key from the native secret store.

## Channels

- `channel info CHANNEL` retrieves public channel metadata. `CHANNEL` may be a handle, channel ID, or supported channel URL.
- `channel search QUERY` returns channel candidates. It never silently selects one.
- `channel analyze CHANNEL` summarizes matching uploads and identifies breakout videos. `CHANNEL` may be a handle, channel ID, or supported channel URL.

### Channel analysis

`channel analyze` defaults to the latest 12 calendar months, ending on today's
UTC date. The default is a calendar-month window, so its start date is clamped
to the same day-of-month when possible (for example, March 31 minus one month
becomes February 28 or 29). Both window endpoints are inclusive.

Choose one window style:

- `--months N` for the latest `N` calendar months (`N` must be positive).
- `--year YYYY` for one UTC calendar year.
- `--from YYYY-MM-DD` and/or `--to YYYY-MM-DD` for explicit UTC boundaries.
- `--all` to analyze the complete public upload history.

Analysis also accepts `--match TEXT` for case-insensitive title matching,
`--limit N` for the number of breakout rows (10 by default), `--refresh` to
bypass cached channel identity data, `--no-color`, `--format table|json`, and
`--output PATH`. The aggregate summary and monthly cohorts always use every
matching upload in the selected window; `--limit` only limits the breakout
section. Explicit `--format csv` is invalid for this heterogeneous report.

The table output has Summary, Monthly publication cohorts, and Breakout videos
sections. Monthly cohort values are current snapshot metrics grouped by publish
month, not historical growth measurements. Breakout multipliers compare a
video's current views with the median current views of matching videos
published in the same year.

## Videos

- `videos list CHANNEL` lists all matching uploads, newest first by default.
- `videos latest CHANNEL` returns the newest matching uploads, 20 by default.
- `videos top CHANNEL` returns the most-viewed matching uploads, 10 by default.
- `videos first CHANNEL` returns the oldest matching upload.

Video commands accept:

- `--match TEXT` for case-insensitive title substring matching.
- `--year YYYY`, or the mutually exclusive `--from YYYY-MM-DD` and `--to YYYY-MM-DD` UTC boundaries.
- `--sort published-asc|published-desc|views|likes`.
- `--limit N`.
- `--format table|json|csv`.
- `--output PATH` to write the result to a file.
- `--refresh` to bypass cached channel identity data.
- `--no-color` to disable terminal styling.

## Quota use

Video commands read the uploads playlist newest first and only request full metadata for uploads that pass `--match`, `--year`, `--from`, and `--to`. Traversal stops early once older uploads can no longer enter the result set, which covers date-bounded queries and newest-first queries with `--limit`. Ranking by `views` or `likes`, and listing without a limit, still read the whole history. `meta.scanned_all` records which happened.

Analysis uses the same newest-first traversal and filtering optimization. It
must inspect every matching upload in the selected window to calculate complete
aggregates, so `--limit` does not reduce the metadata needed for the summary.
Bounded windows can stop once older uploads are outside the window; `--all`
reads the full public history. `meta.scanned_all` records whether traversal
covered the whole upload history.

Plain channel names are intentionally rejected by research commands. Use `channel search`, then pass an exact handle or ID.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Success |
| 2 | Invalid arguments |
| 3 | Missing or rejected credentials |
| 4 | Channel or video not found, or ambiguous input |
| 5 | Network, quota, or upstream YouTube failure |
