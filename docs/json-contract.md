# JSON output contract

JSON output is intended for scripts and agents. Version 0.1.0 emits `schema_version: 1` and writes diagnostics only to stderr.

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
    "warnings": []
  }
}
```

Consumers may ignore unknown object properties. A future incompatible change will increment `schema_version`. Optional API statistics, such as likes or comments, are `null` when unavailable. An absent optional statistic does not remove the video from `items`.

Timestamps use ISO 8601 in UTC. Request counts are estimates grouped by endpoint, not authoritative remaining Google quota.

CSV output has these fixed columns:

```text
video_id,title,url,published_at,duration_seconds,views,likes,comments
```

