<div align="center">

<img src="https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/yt-research-hero.webp" alt="A video play button under a magnifying glass, surrounded by terminal and data-analysis elements">

# yt-research

### YouTube channel research, straight from your terminal.

Explore public channel metadata and upload histories, then export clean data for spreadsheets, scripts, and agents.

[![CI](https://github.com/vedntp/yt-research/actions/workflows/ci.yml/badge.svg)](https://github.com/vedntp/yt-research/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/yt-research?color=blue)](https://pypi.org/project/yt-research/) [![Python](https://img.shields.io/pypi/pyversions/yt-research)](https://pypi.org/project/yt-research/) [![License: MIT](https://img.shields.io/github/license/vedntp/yt-research)](https://github.com/vedntp/yt-research/blob/main/LICENSE)

[Quick start](#quick-start) · [Commands](#commands-at-a-glance) · [Documentation](#documentation) · [Contributing](https://github.com/vedntp/yt-research/blob/main/CONTRIBUTING.md)

</div>

> [!IMPORTANT]
> `yt-research` is under active development. The 0.1.x interface may evolve before 1.0.

---

## ✨ Why yt-research?

The YouTube website is built for watching. `yt-research` is built for answering
questions about a channel's public catalog.

<p align="center"><code>discover</code> &nbsp;→&nbsp; <code>collect</code> &nbsp;→&nbsp; <code>filter</code> &nbsp;→&nbsp; <code>rank</code> &nbsp;→&nbsp; <code>export</code></p>

| | |
| :--- | :--- |
| 🔎 **Resolve precisely**<br>Start from a handle, channel ID, or channel URL. | 🧭 **Search safely**<br>See candidates instead of accepting an ambiguous match. |
| 🗂️ **Walk every upload**<br>Traverse the channel's complete public uploads history. | 🎯 **Slice the catalog**<br>Filter by title text, year, or UTC date range. |
| 📊 **Rank what matters**<br>Sort videos by publication date, views, or likes. | ↗️ **Take data anywhere**<br>Use terminal tables, versioned JSON, or fixed-column CSV. |

It uses the official YouTube Data API v3 with your own API key and requests only
public data. Ambiguous channel searches return candidates instead of silently
choosing one.

## ⚡ Quick start

### 1 · Install

Use [pipx](https://pipx.pypa.io/) with Python 3.11+ on macOS or Linux:

```console
pipx install yt-research
```

### 2 · Authenticate

Add your YouTube Data API key to your operating system's native secret store:

```console
yt-research auth set
yt-research auth status
```

### 3 · Research

Replace the placeholder with a public channel handle:

```console
# See the newest uploads
yt-research videos latest @examplecreator --limit 10

# Find the most-viewed videos published in 2026
yt-research videos top @examplecreator --year 2026

# Search titles and save the results
yt-research videos list @examplecreator --match "tutorial" --format csv --output videos.csv
```

Terminal output defaults to a readable table. Redirected output automatically
switches to JSON, while diagnostics stay on stderr:

```console
yt-research videos list @examplecreator > videos.json
```

> [!TIP]
> Need an API key? Follow the step-by-step [API key setup guide](https://github.com/vedntp/yt-research/blob/main/docs/api-key-setup.md).
> In CI or headless Linux, set `YT_RESEARCH_API_KEY` instead; it takes precedence
> over the native secret store.

<details>
<summary><strong>Other ways to install</strong></summary>

With `uv`:

```console
uv tool install yt-research
```

For a one-off run:

```console
uvx yt-research --help
```

From a development checkout:

```console
git clone https://github.com/vedntp/yt-research.git
cd yt-research
uv sync
uv run yt-research --help
```

</details>

## 🧭 Commands at a glance

| | Command | What it does |
| :---: | :--- | :--- |
| 🔎 | `yt-research channel info CHANNEL` | Show public metadata for one channel |
| 🧭 | `yt-research channel search QUERY` | Return candidates for a channel name |
| ⚡ | `yt-research videos latest CHANNEL` | Show the newest matching uploads |
| 📈 | `yt-research videos top CHANNEL` | Show the most-viewed matching uploads |
| ⏪ | `yt-research videos first CHANNEL` | Find the oldest matching upload |
| 🗂️ | `yt-research videos list CHANNEL` | List and filter a channel's uploads |

Video commands support `--match`, `--year`, `--from`, `--to`, `--sort`, `--limit`,
`--format`, and `--output`. Run any command with `--help` or see the full
[command reference](https://github.com/vedntp/yt-research/blob/main/docs/commands.md).

### Research recipes

<details>
<summary><strong>🔭 Trace a topic through a channel</strong></summary>

```console
yt-research videos list @examplecreator --match "telescope" --sort published-asc
```

Title matching is case-insensitive. Add `--from` and `--to` to narrow the timeline.

</details>

<details>
<summary><strong>🏆 Find a channel's strongest videos from one year</strong></summary>

```console
yt-research videos top @examplecreator --year 2026 --limit 25
```

`videos top` sorts matching uploads by view count and defaults to ten results.

</details>

<details>
<summary><strong>🤖 Build a clean dataset for a script or agent</strong></summary>

```console
yt-research videos list @examplecreator --from 2025-01-01 --format json --output videos.json
```

The output follows a versioned contract and keeps warnings on stderr.

</details>

## 🔌 Built for people and programs

Interactive results are formatted as a styled terminal table:

[![Stylized yt-research terminal preview based on fictional fixture data](https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/terminal-demo.svg)](https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/terminal-demo.svg)

<p align="center"><sub>Stylized preview based on fictional test fixture data · <a href="https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/terminal-demo.svg">open full size</a></sub></p>

The same commands fit cleanly into pipelines and spreadsheet workflows:

```console
# Pipeline → versioned JSON
yt-research videos list @examplecreator --year 2026 | jq '.items[].title'

# Spreadsheet → fixed-column CSV
yt-research videos top @examplecreator --limit 50 --format csv --output top-videos.csv
```

JSON output includes a schema version, command metadata, the resolved channel,
the effective query, result items, and request counts. See the
[JSON output contract](https://github.com/vedntp/yt-research/blob/main/docs/json-contract.md) for the stable shape.

## 📚 Documentation

| Guide | Description |
| :--- | :--- |
| [Command reference](https://github.com/vedntp/yt-research/blob/main/docs/commands.md) | Every command, option, and exit code |
| [API key setup](https://github.com/vedntp/yt-research/blob/main/docs/api-key-setup.md) | Google Cloud setup and credential security |
| [JSON output contract](https://github.com/vedntp/yt-research/blob/main/docs/json-contract.md) | Stable output schema for integrations |
| [Troubleshooting](https://github.com/vedntp/yt-research/blob/main/docs/troubleshooting.md) | Common authentication, quota, and network issues |
| [Codex integration](https://github.com/vedntp/yt-research/blob/main/integrations/codex/README.md) | Optional setup for agent-driven research |

## Scope and privacy

`yt-research` does not use OAuth or access private account data. It does not
download videos, retrieve transcripts or comments, classify Shorts, or run as a
hosted service. API calls consume quota from the Google Cloud project associated
with your key.

## Contributing

Contributions are welcome. Read the [contributing guide](https://github.com/vedntp/yt-research/blob/main/CONTRIBUTING.md),
[Code of Conduct](https://github.com/vedntp/yt-research/blob/main/CODE_OF_CONDUCT.md),
and [Security Policy](https://github.com/vedntp/yt-research/blob/main/SECURITY.md)
before opening a contribution.

## License

Released under the [MIT License](https://github.com/vedntp/yt-research/blob/main/LICENSE).

---

<p align="center"><sub>Built for curious people, repeatable research, and clean data.</sub></p>
