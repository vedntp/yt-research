# Contributing

Thank you for helping improve `yt-research`.

## Development setup

Install [uv](https://docs.astral.sh/uv/), clone the repository, and run:

```console
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Tests must use synthetic data and must not call the live YouTube API. Keep real channel names, credentials, and API responses out of fixtures and bug reports.

## Pull requests

- Open an issue before large changes so the design can be discussed.
- Keep each pull request focused and add tests for changed behavior.
- Update documentation when the public command or output interface changes.
- Add a changelog entry under `Unreleased` for user-visible changes.
- Ensure all checks pass on Python 3.11 or newer.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

