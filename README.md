# yt-research

`yt-research` is an open source command-line tool for exploring public YouTube channel metadata and upload histories. It produces readable terminal tables for people and stable JSON or CSV for scripts and agents.

> [!IMPORTANT]
> This project is under active development. Version 0.1.0 is the first public interface and may evolve before 1.0.

## What it does

- Resolve a channel by handle, channel ID, or channel URL.
- Search for channel candidates without silently choosing an ambiguous match.
- Walk a channel's complete public uploads playlist.
- Filter videos by title text or UTC publication date.
- Sort by publication date, views, or likes.
- Export versioned JSON and fixed-column CSV.

`yt-research` uses the official YouTube Data API v3. You provide your own API key, and the tool only requests public data.

## Install

Python 3.11 or newer is required. The supported platforms are macOS and Linux.

```console
pipx install yt-research
```

Alternatively, use `uv`:

```console
uv tool install yt-research
```

Or run it without a persistent installation:

```console
uvx yt-research --help
```

For a development checkout:

```console
git clone https://github.com/vp275/yt-research.git
cd yt-research
uv sync
uv run yt-research --help
```

## Configure an API key

Create an API key for the YouTube Data API v3, then store it in your operating system's native secret store:

```console
yt-research auth set
yt-research auth status
```

For CI or headless Linux, set the environment variable instead:

```console
export YT_RESEARCH_API_KEY="your-api-key"
```

The environment variable takes precedence over the native secret store. See [API key setup](docs/api-key-setup.md) for complete instructions and security guidance.

## Quick start

Use a fictional placeholder handle in examples, replacing it with the public channel you want to research:

```console
yt-research channel info @examplecreator
yt-research channel search "Example Creator"
yt-research videos latest @examplecreator --limit 20
yt-research videos top @examplecreator --year 2026 --limit 10
yt-research videos first @examplecreator --match "tutorial"
yt-research videos list @examplecreator --from 2025-01-01 --format json
```

When stdout is a terminal, results default to a table. Redirected output defaults to JSON:

```console
yt-research videos list @examplecreator > videos.json
yt-research videos list @examplecreator --format csv --output videos.csv
```

Diagnostics and warnings are written to stderr, so JSON and CSV on stdout remain machine-readable.

## Documentation

- [Command reference](docs/commands.md)
- [JSON output contract](docs/json-contract.md)
- [API key setup](docs/api-key-setup.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Optional Codex integration](integrations/codex/README.md)

## Privacy and limitations

The tool does not use OAuth or access private account data. Version 0.1.0 does not download videos, retrieve transcripts or comments, classify Shorts, or run as a hosted service. API calls consume quota from the Google Cloud project associated with your key.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), the [Code of Conduct](CODE_OF_CONDUCT.md), and the [Security Policy](SECURITY.md) before opening a contribution.

## License

MIT. See [LICENSE](LICENSE).
