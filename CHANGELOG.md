# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [1.0.1] - 2026-04-08

### Added

- Step-based processing logs for each transcript, including download, summary generation, markdown rendering, upload, and completion markers.
- Regression tests covering transient Drive `BrokenPipeError` retries and Ollama timeout fallback behavior.

### Changed

- Increased pipeline visibility with richer Drive export, PDF render, upload routing, and Ollama response-size logging.
- Updated the Ollama summarization flow to retry once at 600 seconds before falling back to a 10-chunk extraction path.

### Fixed

- Retried transient Google Drive and Google Docs request failures, including retryable HTTP statuses and transport exceptions such as `BrokenPipeError`, socket timeouts, and `ssl.SSLEOFError`.
- Reduced repeated cron failures for long transcripts by making single-pass Ollama requests more resilient before chunk fallback.

## [1.0.0] - 2026-04-08

### Added

- Initial packaged `minutes` release with Google Drive transcript ingestion, summary generation, and multi-format output support.
- Cron runner support and operational scripts for scheduled processing.
