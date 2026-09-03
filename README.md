<div align="center">

<img src="https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/yt-research-hero.webp" alt="A video play button under a magnifying glass, surrounded by terminal and data-analysis elements">

# yt-research

### Export and analyze a YouTube channel's complete public video history from your terminal.

Explore channel metadata, find top videos, and export clean CSV or JSON for spreadsheets, scripts, and agents.

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

Replace `@examplecreator` with an exact channel handle, channel ID, or YouTube
channel URL. These common commands work without any flags:

```console
# Show public channel metadata
yt-research channel info @examplecreator

# See the newest 20 uploads
yt-research videos latest @examplecreator

# Find the 10 most-viewed uploads
yt-research videos top @examplecreator

# List the newest 10 uploads
yt-research videos list @examplecreator

# Summarize the latest 12 months and surface 10 breakout uploads
yt-research channel analyze @examplecreator
```

Terminal output defaults to a readable table. Redirected output switches to
JSON, while diagnostics stay on stderr:

```console
yt-research videos list @examplecreator > videos.json
```

Use flags only to refine the question: `--year 2026`, `--match "tutorial"`,
`--limit 50`, `--format csv`, or `--output results.json`. Run any command with
`--help` to see its complete set of options.

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

## 🧭 Commands and defaults

| | Command | Default result |
| :---: | :--- | :--- |
| 🔎 | `yt-research channel info CHANNEL` | Public metadata for one channel |
| 🧭 | `yt-research channel search QUERY` | Up to 10 candidates for an ambiguous name |
| ⚡ | `yt-research videos latest CHANNEL` | Newest 20 uploads |
| 📈 | `yt-research videos top CHANNEL` | 10 most-viewed uploads across the history |
| ⏪ | `yt-research videos first CHANNEL` | Oldest upload |
| 🗂️ | `yt-research videos list CHANNEL` | Newest 10 uploads |
| 📊 | `yt-research channel analyze CHANNEL` | Last 12 months, with 10 breakout uploads |

Channel-specific research commands accept an exact channel handle, channel ID,
or supported YouTube channel URL. Plain names are intentionally not guessed:
use `channel search`, then pass the handle or ID you select.

### Refine a result when needed

- `--match TEXT` limits videos to a case-insensitive title match.
- `--year YYYY`, `--from YYYY-MM-DD`, and `--to YYYY-MM-DD` select a UTC
  publication window.
- `--limit N` changes how many video rows are returned.
- `--format table|json|csv` selects the output format; analysis supports table
  and JSON because its report contains several sections.
- `--output PATH` writes the result to a file instead of stdout.

For `channel analyze`, use `--months N`, `--year YYYY`, `--from`/`--to`, or
`--all` to change the 12-month default window. Its aggregate summary always
uses every matching upload in that window; `--limit` changes only the
breakout-video rows. See the full
[command reference](https://github.com/vedntp/yt-research/blob/main/docs/commands.md)
for every option and exit code.

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
<summary><strong>📊 Understand a channel's recent performance</strong></summary>

```console
yt-research channel analyze @examplecreator --match "tutorial"
```

The report includes total and median performance, engagement rates, upload
cadence, publication-month cohorts, and year-normalized breakout videos. Cohort
metrics are current snapshots grouped by the month a video was published; they
do not represent historical view growth. Use `--format json` for automation.

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

[![Animated yt-research terminal demo using illustrative MKBHD data](https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/yt-research-demo.gif)](https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/yt-research-demo.gif)

<p align="center"><sub>Illustrative demo; titles and statistics are not actual MKBHD data · <a href="https://raw.githubusercontent.com/vedntp/yt-research/main/docs/assets/yt-research-demo.gif">open full size</a></sub></p>

The same commands fit cleanly into pipelines and spreadsheet workflows:

```console
# Pipeline → versioned JSON
yt-research videos list @examplecreator --year 2026 | jq '.items[].title'

# Spreadsheet → fixed-column CSV
yt-research videos top @examplecreator --limit 50 --format csv --output top-videos.csv
```

JSON output includes a schema version, command metadata, the resolved channel,
the effective query, result items, and request counts. Analysis reports add
typed summary and publication-cohort sections while retaining the same envelope.
See the
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
with your key. Analysis reports may traverse every upload in the selected
window because aggregate metrics must not be truncated; use a bounded date
window and title match to keep quota use focused.

## Contributing

Contributions are welcome. Read the [contributing guide](https://github.com/vedntp/yt-research/blob/main/CONTRIBUTING.md),
[Code of Conduct](https://github.com/vedntp/yt-research/blob/main/CODE_OF_CONDUCT.md),
and [Security Policy](https://github.com/vedntp/yt-research/blob/main/SECURITY.md)
before opening a contribution.

## License

Released under the [MIT License](https://github.com/vedntp/yt-research/blob/main/LICENSE).

---

<p align="center"><sub>Built for curious people, repeatable research, and clean data.</sub></p>
