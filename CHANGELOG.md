## v2.8.2 — Inotify Initial Scan Fix

- Fixed: inotify watcher mode did not scan existing files on startup — files already sitting in Comics_in, Books_in, or Comics_raw when the container started were silently ignored; an initial scan now runs before the observer starts

# Changelog

## v2.8.1 — Project Structure Cleanup

- Fixed: Dockerfile was hardcoding pip dependencies instead of installing from `requirements.txt`; now uses `COPY requirements.txt` + `pip install -r` for proper layer caching
- Fixed: CI workflow hardcoded `pip install flask pytest` instead of using `requirements-dev.txt`
- Fixed: `requirements-dev.txt` only contained `pytest` — added `flask` and `watchdog` so it reflects what tests actually need
- Added: `pyproject.toml` with project metadata and pytest configuration (`testpaths = ["tests"]`)

## v2.8.0 — inotify Watcher Mode & WebUI Improvements

- Added: inotify watcher mode — instant file detection on local filesystems; poll remains the default and works everywhere including network shares (NFS, SMB)
- Added: Bindery Settings card in WebUI — Watcher Mode selector and File Stability Timeout field
- Added: Save & Restart button — saves settings and restarts the container in one step; page auto-reloads when healthy
- Added: `/api/restart` endpoint
- Added: `/api/logs` endpoint — activity log live-polls every 5 s instead of requiring a page reload
- Added: persistent log at `/app/config/bindery.log` — survives restarts, pre-loaded into UI on startup (trimmed to 5000 lines)
- Added: `File Stability Timeout` setting in WebUI (10–300 s, default 60)
- Fixed: `kcc_borders`, `kcc_gamma`, `kcc_profile`, `kcc_format`, `kcc_cropping`, `kcc_splitter`, and `kcc_batchsplit` were unvalidated — invalid POST values now fall back to safe defaults
- Fixed: kepubify pinned to v4.0.4 in Dockerfile — was previously downloading `latest` at build time
- Improved: page subtitle reflects active watcher mode (polling vs inotify)
- Improved: SVG logo header replaces plain text title
- Added: 20 new tests covering `_build_kcc_cmd`, `process_file` error paths, `scan_directories`, `_validate_post`, and `/api/logs`

## v2.7.1 — WebUI Polish

- Fixed: reMarkable device profiles now use a Jinja for loop, consistent with Kindle and Kobo
- Fixed: log section h2 used inline styles to fight its own class rules — replaced with `.log-title` modifier class
- Fixed: version line used a fragile negative margin — now a proper `.version` class in natural document flow
- Fixed: Output Metadata checks div used an inline `margin-bottom` — replaced with `.checks-spaced` class
- Improved: Custom Profile Resolution fields (width, height, note) are now hidden unless Generic / Custom profile is selected
- Improved: KCC log no longer emits a redundant STARTING line before QUEUED — comics now log QUEUED then CMD


## v2.7.0 — Device Profiles & Borders Overhaul
- Fixed: incorrect KCC profile keys — `K578` split into correct `K57` (Kindle 5/7) and `K810` (Kindle 8/10); `KPW3` corrected to `KPW34`; `KoM`+`KoT` merged to correct `KoMT` (Kobo Mini/Touch); `KoCE` corrected to `KoCC` (Kobo Clara Colour); removed `KoE2` (no KCC profile exists)
- Added missing KCC profiles: `K11` (Kindle 11), `KCS` (Kindle Colorsoft), `KS3` (Kindle Scribe 3), `KSCS` (Kindle Scribe Colorsoft), `KS1860`, `KS1920`, `KoN` (Kobo Nia), `KoS` (Kobo Sage), `RmkPPMove` (reMarkable Paper Pro Move)
- Updated `KO` label to include Paperwhite 12; updated `KS` label to Scribe 1/2
- Changed: Borders setting replaced two checkboxes (Black Borders / White Borders) with a single dropdown (None / Black / White)
- Note: existing `settings.json` files will get the new `kcc_borders` key defaulting to `black` on next save

## v2.6.0 — Refactor & Housekeeping
- Added `requirements.txt` listing production dependencies (Flask, gunicorn, packaging, kcc)
- Fixed: `comics_raw/` added to `.gitignore` to prevent accidentally tracking dropped image files
- Fixed: `test_processor.py` mock config now imports directly from `config.py` instead of using a stale hardcoded fallback dict
- Refactored: `app.py` now uses a `create_app()` factory — background threads no longer start at import time, removing the need for the import-time `threading.Thread` patch in `conftest.py`
- Refactored: `_build_kcc_cmd` extracted from `process_file` in `processor.py` — KCC argument building is now a standalone testable function
- Added module docstrings to all Python modules
- Added docstrings to previously undocumented functions
- Added type hints to all function signatures across `app.py`, `config.py`, `processor.py`, and `raw_processor.py`
- Added `ConfigDict` type alias in `config.py` for the shared settings dictionary type

## v2.5.0 — Bug Fixes

- Fixed: gunicorn "Control server error: Permission denied" on every container start — disabled the unused control socket introduced in gunicorn 25.1.0
- Fixed: files that convert successfully but produce no output were retried on every scan instead of being flagged `.failed`
- Fixed: unexpected exceptions in `process_file` (e.g. permission errors, disk full) left the source file untouched and retried forever — now renamed `.failed` same as other failure paths
- Fixed: raw folders that hit an unexpected error during zipping were left in `Comics_raw` and retried forever — they are now moved to `Comics_raw/unprocessed/` like other failures
- Fixed: subdirectory path calculation for files in the root of `Comics_in` / `Books_in` used the wrong `os.path` call order (worked by accident; now correct)
- Fixed: `load_config` and `save_config` had no locking — concurrent conversion threads reading config while a POST was writing it could get partial JSON and silently fall back to defaults
- Fixed: `settings.json` could be left truncated if the process was killed mid-write — write is now atomic via temp file + `os.replace()`
- Fixed: WebUI accepted non-numeric input for `croppingpower`, `croppingminimum`, `customwidth`, and `customheight` — values are now validated and clamped before saving
- Improved: `entrypoint.sh` `chown` no longer walks every file in all volumes on every container start — only files not already owned by `abc` are touched
- Added comment to `wait_for_file_ready` explaining the 60s timeout and why SKIP does not rename to `.failed`
- Added warning comment in `app.py` explaining why `--preload` must not be added to gunicorn

## v2.4.0 — Docker Hub Image

- Bindery is now available as a pre-built image at `dinkeyes/bindery` on Docker Hub — no clone or build step required
- Added GitHub Actions workflow to automatically build and push images on each release
- Updated README with Docker Hub quick start and updated compose example

## v2.3.2 — Housekeeping

- Fixed: WebUI version number was not updated in previous releases

## v2.3.1 — Bug Fix

- Fixed: duplicate files in `comics_out` and `books_out` were silently overwritten — output files are now collision-safe and will be named `file_2.kepub`, `file_3.kepub` etc if a file with the same name already exists
  
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
