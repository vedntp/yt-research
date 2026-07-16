# Troubleshooting

## No API key is available

Run `yt-research auth set`. On headless Linux, set `YT_RESEARCH_API_KEY` in the process environment instead.

## The API rejects the key

Confirm that YouTube Data API v3 is enabled in the key's Google Cloud project and that API restrictions allow it. Revoke and replace any key that may have been exposed.

## Quota has been exceeded

Quota is managed by Google Cloud. Wait for quota reset or review the project's quota allocation. `yt-research` reports request estimates but cannot determine the authoritative quota remaining.

## A channel name is ambiguous

Research commands require a channel handle, channel ID, or supported URL. Run `yt-research channel search "name"`, inspect the candidates, and retry with the exact handle or ID.

## A statistic is null

YouTube may hide or omit likes, comments, or subscriber counts. The tool preserves the record and represents the unavailable value as `null`.

## Results appear stale

Live video and channel statistics are fetched for each research operation. If a channel identity has changed, add `--refresh` to bypass the local identity cache.

