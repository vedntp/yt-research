# Changelog

All notable changes to this project are documented here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Video commands now filter uploads using playlist metadata and stop traversing once older uploads cannot enter the result set, so date-bounded and newest-first queries cost a fraction of the previous API quota.

### Added

- `meta.scanned_all` reports whether a report read the channel's whole upload history.
- Added `yt-research channel analyze` for 12-month, custom-window, or full-history channel summaries, publication-month cohorts, and year-normalized breakout videos. Analysis JSON retains the common versioned envelope, and its table output clearly distinguishes current snapshots from historical growth.

## [0.1.1] - 2026-09-03

### Changed

- Redesigned the project and package landing page with clearer onboarding, research recipes, and accessible visual examples.

## [0.1.0] - 2026-07-31

### Added

- Added `yt-research --version` for checking the installed release.
- Initial public CLI for researching public YouTube channels and upload histories.
- Human-readable tables and stable JSON and CSV output.
- Native secret-store support and an environment variable for headless use.
- Synthetic test suite and macOS and Linux continuous integration.

[Unreleased]: https://github.com/vedntp/yt-research/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/vedntp/yt-research/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/vedntp/yt-research/releases/tag/v0.1.0
