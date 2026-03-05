# Changelog

## v2.3.0 — Comics Raw Pipeline

- Added `Comics_raw` folder — drop a flat folder of images and Bindery automatically zips it into a CBZ and feeds it into the normal KCC pipeline
- Folders with subfolders or no images are moved to `Comics_raw/unprocessed/` with a clear log message explaining why
- Original folders moved to `Comics_raw/processed/` on success
- Collision-safe naming if a CBZ with the same name already exists in `Comics_in`
- Raw folders held until stable (no file changes for 30 s) before processing, so mid-transfer folders are never zipped
- Fixed: `entrypoint.sh` now chowns `/Comics_raw` so no manual permission fix is needed on first run
- 16 new tests covering the full raw pipeline

## v2.2.0 — Tests, Health Endpoint & Batch Split Fix

- Added test suite (19 tests covering config, processor logic, and Flask routes)
- Added `/health` endpoint and Docker `HEALTHCHECK`
- Fixed silent data loss when `kcc_batchsplit` produces multiple output files
- Fixed `ConversionError` class definition order
- Added `requirements-dev.txt` for running tests locally

## v2.1.0 — Concurrent Conversion Fix

- Fixed a bug where multiple comics dropped at once could cause KCC to fail with "Failed to extract archive" due to concurrent execution
- KCC conversions now queue and run one at a time (kepubify/books are unaffected and still run in parallel)
- Added `QUEUED` log status so you can see when a file is waiting for a slot
- Improved log prefix length (40 chars) so long filenames are distinguishable
- Temp paths are now pure UUIDs, eliminating any risk of filename-based conflicts in /tmp
- Cleaner internal error handling with a dedicated `ConversionError` class

## v2.0.0 — Code Refactor

- Refactored from a single-file app into a proper package structure
  - `config.py` — settings management
  - `processor.py` — file watching and conversion logic
  - `templates/index.html` — HTML template extracted from Python
  - `app.py` — lean Flask entry point

## v1.0.0 — Stable Release

- Automated folder watching (every 10 seconds) for Books and Comics
- Full WebUI for real-time KCC and kepubify configuration
- Native Kobo support (auto-renaming `.kepub.epub` to `.kepub`)
- NAS-friendly polling architecture (SMB/NFS compatible)
- Production-ready Docker setup with PUID/PGID support and log rotation
