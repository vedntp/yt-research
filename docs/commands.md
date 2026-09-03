# Command reference

Run `yt-research COMMAND --help` for the authoritative options installed with your version.

## Authentication

- `auth set` stores an API key in the native secret store.
- `auth status` reports whether a key is available and where it came from, without displaying it.
- `auth delete` removes the key from the native secret store.

## Channels

- `channel info CHANNEL` retrieves public channel metadata. `CHANNEL` may be a handle, channel ID, or supported channel URL.
- `channel search QUERY` returns channel candidates. It never silently selects one.

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

Plain channel names are intentionally rejected by research commands. Use `channel search`, then pass an exact handle or ID.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Success |
| 2 | Invalid arguments |
| 3 | Missing or rejected credentials |
| 4 | Channel or video not found, or ambiguous input |
| 5 | Network, quota, or upstream YouTube failure |

