# Codex integration

Codex can call `yt-research` as a local research tool. This integration is optional and never modifies global Codex configuration automatically.

1. Install and configure `yt-research`.
2. Copy the sample instructions below into the relevant workspace `AGENTS.md`, adapting them to your project.
3. Ensure the Codex process can access `YT_RESEARCH_API_KEY` or the native secret store.

```markdown
## YouTube research

Use the relevant `yt-research` command with `--format json` for public YouTube channel and upload-history research, for example `yt-research videos list @channelhandle --format json`. Pass an exact channel handle, ID, or URL. Use `yt-research channel search` only when the user supplied an ambiguous channel name. Treat stdout as structured data and stderr as diagnostics.
```

Do not ask Codex to expose, print, or persist the API key.
