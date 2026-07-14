## v4.0.0

- Added: **Bundle Chapter Folders** toggle in Bindery Settings — with it on, a folder of chapter archives (`.cbz`/`.cbr`/`.zip`/`.rar`) dropped into `Comics_in` converts as one volume with a chapter per file, ordered naturally (`ch2` before `ch10`), instead of one book per file. Off by default, so existing per-file setups are untouched; folders holding PDFs or loose images alongside archives keep the per-file path either way
- Changed: the quiet window before a dropped folder converts now follows **File Stability Timeout** (with a 30 s floor) instead of a fixed 30 s, so slow downloaders that pause between chapters can extend it

## v3.6.0 — MozJPEG

- Added: **MozJPEG** toggle in Color and Quality — exposes KCC's `--mozjpeg`, which losslessly recompresses the JPEG pages inside the output book; the pixels are untouched, the files just get smaller, at the cost of slower conversion. Off by default

## v3.5.0 — Rainbow Eraser

- Added: **Rainbow Eraser** toggle in Color and Quality — exposes KCC's `--eraserainbow`, which attenuates the interference pattern that colour e-ink screens (Kindle Colorsoft, Kobo Libra Colour) add to colour pages; off by default and only affects colour output

## v3.4.0 — Folder Volumes, Format Cleanup & Watcher Fixes

- Added: drop a folder of images into `Comics_in` and it converts as one bundled volume named after the folder (subfolders become chapters); folders containing comic archives convert file-by-file with structure preserved instead, since KCC rejects nested archives — both work with Retry and Preserve Originals
- Fixed: the scanner descended into `<name>.failed` folders and converted the archives inside, silently consuming a failed job's source files — `.failed` directories are now excluded everywhere
- Removed: `MOBI` and `KFX` output formats — MOBI needs Amazon's abandoned kindlegen binary and KFX a Calibre plugin, neither of which exists in the image, so every such conversion failed; saved configs fall back to `EPUB`, which Kindles accept via Send to Kindle
- Fixed: **Cropping Minimum** was sent to KCC unconverted, but KCC expects a 0–1 ratio rather than a percentage — the old default of `1` suppressed cropping entirely; the value is now divided by 100 and the default is `0`
- Fixed: inotify mode never processed `Comics_in` folder jobs (their events fire while the folder is still copying) and could convert-and-delete files inside a folder job individually; folder contents now route to their folder job, and a 60 s backstop scan catches whatever events miss — which also un-strands files on network mounts and slow `Comics_raw` copies
- Fixed: repeated failures no longer collide — `.failed` renames pick a free name (`X_2.failed`), the job remembers the real path so Retry still finds it, and Retry refuses to overwrite a newly dropped file with the same name
- Fixed: Preserve Originals archive moves are collision-safe instead of overwriting files or nesting folders
- Fixed: the live activity log froze once its 300-line buffer filled — the WebUI now detects buffer rotation, not just growth
- Fixed: jobs interrupted by a container restart stayed as permanent "processing" rows — they're cleared on startup and the source files simply re-queue
- Fixed: files whose names start with a dash (`-Batman.cbz`) failed to convert — the title is now passed in `=` form and the source gets a logged rename, since 7z inside KCC reads a bare dash-leading filename as a switch
- Improved: WebUI reworked — status, file browser, and activity log moved above the settings form, low-contrast hint/label text fixed, mobile layout no longer crushes the status table, touch-sized buttons, keyboard focus outlines, and friendlier empty states
- Updated: KCC `v9.4.3` → `v10.3.0` — better PDF handling (rasterised via PyMuPDF instead of extracting embedded JPEGs) plus five months of upstream image-processing fixes including the v10 major release; all flags, device profiles, and behaviour Bindery relies on verified unchanged
- Improved: KCC is now installed without its GUI dependency chain — PySide6/Qt never belonged in a headless image and dropping it makes the image several hundred MB smaller
- Removed: stale `patch.py` release script and the unused `packaging` dependency; gunicorn is pinned `>=25.1` for `--no-control-socket`
- Updated: GitHub Actions bumped to current majors (checkout v5, setup-python v6, docker actions v4/v6/v7)

## v3.3.1 — Fix Startup Crash When SKIP_CHOWN Unset

- Fixed: `entrypoint.sh` crashed on startup with `SKIP_CHOWN: unbound variable` whenever the `SKIP_CHOWN` environment variable was not set — the script runs under `set -u` and the `${SKIP_CHOWN,,}` expansion had no default, so any setup that never opted into `SKIP_CHOWN` (i.e. the default for everyone) failed to start. `SKIP_CHOWN` now defaults to `false`, mirroring the existing `PUID`/`PGID` pattern; behaviour is unchanged when it is set explicitly

## v3.3.0 — PDF Support for Comics

- Added: `.pdf` is now recognised as a comic input format — drop PDFs into `Comics_in` and they'll be picked up by both the poll scan and inotify watcher, then converted with KCC; KCC supports PDF as a first-class input alongside CBZ/CBR
- Note: EPUBs continue to be handled by the books pipeline (kepubify); KCC does not accept EPUB as input, so graphic-novel EPUBs should be dropped in `Books_in`

## v3.2.0 — Optional chown Skip

- Added `SKIP_CHOWN` environment variable — set to `true` to skip the initial chown step entirely
- Useful for setups where the container cannot chown its volumes but access works regardless, such as NFS mounts inside unprivileged LXC containers
- Default behaviour is unchanged — chown still runs unless `SKIP_CHOWN=true` is explicitly set

## v3.1.1 — Skip Dot-Folders

- Fixed: Bindery was scanning inside dot-folders (`.stfolder`, `.stversions`, etc.) — any directory whose name starts with `.` is now skipped universally in both poll and inotify modes; covers Syncthing and any other tool that creates hidden directories inside watched folders

## v3.1.0 — Preserve Originals

- Added: **Preserve Originals** toggle in Bindery Settings — when enabled, source files in `Comics_in` are moved to `Comics_in/.archive` (mirroring subfolder structure) after a successful conversion instead of being deleted; `.archive` is never scanned or reprocessed
- Fixed: `pyproject.toml` version was out of sync with app version (was `2.8.1`)
- Fixed: `CHANGELOG.md` had an empty `v3.0.1` heading and inconsistent entry format — standardised to `## vX.Y.Z — Description` throughout

## v3.0.2 — Bug Fixes & Housekeeping

- Fixed: `wait_for_file_ready` required only a single 2-second stable-size window — copy tools like FileBrowser can pause mid-write, causing Bindery to convert a partial file and rename it `.failed`; the fix requires **three** consecutive stable readings (~6 s) before a file is considered ready
- Added: inotify mode — `on_closed` handler for `IN_CLOSE_WRITE` fires only after the write handle closes, providing a definitive transfer-complete signal; `on_created` is retained as an earlier trigger
- Fixed: `entrypoint.sh` crashed on startup when `PUID`/`PGID` matched an existing system UID/GID — added `--non-unique` to `groupadd` and `useradd`
- Fixed: `wait_for_file_ready` waited up to 2 s less than configured on odd timeout values — loop count now uses ceiling division
- Fixed: `_notify` used hardcoded `True` fallbacks instead of `DEFAULT_CONFIG` values — now consistent if defaults ever change
- Improved: comic conversions now log `>>> STARTING` when the KCC semaphore is acquired, matching book conversion log style
- Added: `.dockerignore` to reduce Docker build context (excludes tests, assets, docs, and dev files)
- Added: `apprise` to `requirements-dev.txt` so notification tests can run in CI
- Added: 5 unit tests covering `_notify` (no URLs, suppressed success, suppressed failure, success fires, failure fires with error)
- Fixed: removed dead `mock_threading.Lock` setup line from `test_scan_directories_dispatches_comic`
- Fixed: removed orphaned `# Changelog` heading stranded mid-file in `CHANGELOG.md`

## v3.0.0 — Status, File Browser & Notifications

- Added: Processing Status card — live table showing every job (queued / processing / success / failed) with timestamps, duration, and a Retry button for failed files; persisted across restarts in `/app/config/jobs.json` (capped at 500 entries)
- Added: File Browser card — browse and download files from Books_out and Comics_out directly from the UI; no Samba or SSH required
- Added: Notifications via Apprise — configure one or more service URLs (ntfy, Discord, Slack, Telegram, Pushover, email, and 60+ others) with separate toggles for success and failure events
- Added: `/api/status` endpoint — returns full job registry as JSON, sorted newest first
- Added: `/api/retry` endpoint — re-queues a failed job by ID
- Added: `/api/files` endpoint — lists output files with name, size, and mtime
- Fixed: Save Configuration button moved below all settings cards so it clearly saves KCC and Bindery Settings together
- Added: `/api/files/download` endpoint — serves output files as downloads with path-traversal protection

## v2.8.2 — Inotify Initial Scan Fix

- Fixed: inotify watcher mode did not scan existing files on startup — files already sitting in Comics_in, Books_in, or Comics_raw when the container started were silently ignored; an initial scan now runs before the observer starts

## v2.8.1 — Bug Fixes & Project Structure

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

## v2.6.0 — Housekeeping
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

Versions before 2.4.0 predate this changelog.
