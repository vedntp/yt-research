# JSON output contract

JSON output is intended for scripts and agents. The current contract emits
`schema_version: 1` and writes diagnostics only to stderr.

```json
{
  "schema_version": 1,
  "command": "videos.top",
  "fetched_at": "2026-07-17T12:00:00Z",
  "channel": {},
  "query": {},
  "items": [],
  "meta": {
    "matched": 0,
    "returned": 0,
    "requests": {},
    "warnings": [],
    "truncated": false,
    "scanned_all": true
  }
}
```

`scanned_all` reports whether the whole upload history was read. When it is `false`, traversal stopped once the remaining uploads could no longer enter the result set, and `matched` is a lower bound rather than a catalog-wide total.

Consumers may ignore unknown object properties. A future incompatible change will increment `schema_version`. Optional API statistics, such as likes or comments, are `null` when unavailable. An absent optional statistic does not remove the video from `items`.

Timestamps use ISO 8601 in UTC. Request counts are estimates grouped by endpoint, not authoritative remaining Google quota.

## Channel analysis

`channel analyze CHANNEL` keeps the same top-level envelope and emits
`command: "channel.analyze"`. Its default query window is the latest 12
calendar months through the current UTC date. Whichever window style the user
selects, `query.date_from` and `query.date_to` contain its effective inclusive
boundaries; both are `null` for `--all`. `query.match_text` records an optional
case-insensitive title filter, and `query.limit` records the breakout-row limit,
which defaults to 10.

An analysis response has these additional sections:

```json
{
  "summary": {
    "video_count": 0,
    "published_from": null,
    "published_to": null,
    "total_views": 0,
    "median_views": null,
    "median_likes": null,
    "median_comments": null,
    "median_duration_seconds": null,
    "like_rate": null,
    "comment_rate": null,
    "uploads_per_month": null,
    "median_days_between_uploads": null,
    "coverage": {
      "views": 0,
      "likes": 0,
      "comments": 0,
      "duration": 0,
      "like_rate": 0,
      "comment_rate": 0
    }
  },
  "monthly_cohorts": [
    {
      "month": "2026-02",
      "video_count": 0,
      "total_views": 0,
      "median_views": null,
      "like_rate": null,
      "comment_rate": null,
      "median_duration_seconds": null
    }
  ],
  "items": [
    {
      "video_id": "...",
      "title": "...",
      "url": "https://www.youtube.com/watch?v=...",
      "published_at": "2026-02-03T11:00:00Z",
      "duration_seconds": 120,
      "views": 1000,
      "likes": 50,
      "comments": 4,
      "year_median_views": 400,
      "year_cohort_size": 8,
      "view_multiplier": 2.5
    }
  ]
}
```

`summary` describes all matching uploads in the selected window. `like_rate`
and `comment_rate` are aggregate paired counts divided by aggregate views;
they are `null` when the required values are unavailable. Each `coverage`
count reports how many matching videos supplied that metric; the rate counts
only include videos with both the engagement metric and a positive view count.
`monthly_cohorts`
includes zero-upload calendar months inside a bounded window when applicable.
Its metrics are current snapshots grouped by publication month, not a history
of how views changed over time. Breakout `items` are ranked by current
`view_multiplier` against the median current views of matching videos from the
same publication year; rows without a comparable, nonzero year median are
excluded. The breakout `--limit` does not change `summary` or
`monthly_cohorts`.

Analysis reports do not support CSV because their summary, cohort, and video
sections have different shapes. Requesting CSV returns exit code 2.

CSV output has these fixed columns:

```text
video_id,title,url,published_at,duration_seconds,views,likes,comments
```
