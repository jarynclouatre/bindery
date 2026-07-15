## v4.2.0: Light Mode, Dashboards & ComicInfo

Three additions aimed at making Bindery nicer to live with and easier to keep an eye on.

### Added

- **Light theme**: the WebUI now follows your system's light or dark setting, with a toggle in the header that remembers your choice. The activity log keeps its terminal look in both.
- **`/api/stats` for dashboards**: a small JSON endpoint reporting lifetime conversions, space saved, and the live queue, ready for a [Homepage](https://gethomepage.dev/) widget or an Uptime Kuma monitor. Setup is in the README.
- **Use ComicInfo.xml metadata**: turn it on in the KCC settings and Bindery reads the series, number, and title from a comic's embedded `ComicInfo.xml`, so a file named `Chapter 1 (2).cbz` still arrives on your reader as *Berserk #001: The Black Swordsman*. Off by default; falls back to the filename when there's no metadata.

### Note

- The image is multi-arch and always has been, x86 and ARM64 both, so a Raspberry Pi or ARM NAS works too. This is now called out in the README.

## v4.1.0: Keep Originals In Place

A small release for anyone who keeps their comics in a library manager: leave the source file exactly where it is.

### Added

- **Keep in place**: the Originals setting has a new option that leaves a source comic right where it is after it converts, instead of deleting it or moving it to `.archive`. Point `Comics_in` and `Comics_out` at the same folder and the original and the converted book end up side by side, which is what tools like Calibre, Kavita, and BookOrbit expect. Bindery keeps a small record of what it has already converted, so a kept source is never re-converted on the next scan, and re-converts on its own only if you drop a changed copy over it. Thanks to @thevanburenboy for the clear write-up in #13.

### Changed

- **Preserve Originals** is now a three-way **Originals** setting: Delete after converting (the default), Move to `Comics_in/.archive`, or Keep in place. Existing settings migrate automatically, so nothing changes unless you pick the new option.

## v4.0.0: Device Profiles, Browser Upload & Merged Volumes

### Added

- **Device Profiles**: create named profiles in the WebUI (`kobo`, `kindle`, ...), each with its own KCC settings and its own drop folder. `Comics_in/kobo` converts for the Kobo and lands in `Comics_out/kobo`; `Comics_in/kindle` for the Kindle. Drops in the root of `Comics_in` behave exactly as they always have, and nothing changes until you create your first profile.
- **Upload from the browser**: drag files onto the WebUI (or tap the strip on a phone) and they land in the right watch folder, including profile folders. No network shares or shell access needed.
- **Bundle Chapter Folders**: turn it on and a folder of chapter archives (`.cbz`/`.cbr`/`.zip`/`.rar`) converts as ONE volume with a chapter per file in natural order, instead of one book per chapter. Off by default; per-file conversion stays the default behaviour. Thanks to @Elrict for pushing on this back in #9. Folders of chapter files now bundle properly, not just folders of images.
- **Size savings**: successful conversions show before → after sizes and the percentage saved in the status table.

### Improved

- The WebUI got a full visual refresh.

### Updated

- KCC `v10.3.0` → `v10.4.0`: smart-cover-crop crash fix and higher JPEG quality on Scribe/Colorsoft profiles

## v3.6.0: MozJPEG

KCC's MozJPEG option is now a toggle in the WebUI. Turn it on and the JPEG pages inside the output book get losslessly recompressed with the MozJPEG encoder: identical pixels, smaller files, at the cost of somewhat slower conversion.

### Added

- MozJPEG toggle under Color and Quality. Passes KCC's `--mozjpeg`, which reoptimises every JPEG page losslessly. Off by default since it slows processing.

Thanks to @Brandyii for the suggestion (#11).

## v3.5.0: Rainbow Eraser

KCC's rainbow eraser is now a toggle in the WebUI. Turn it on and colour pages get the interference pattern that colour e-ink screens introduce attenuated on the way through, the same option KCC exposes for devices like the Kindle Colorsoft and Kobo Libra Colour.

### Added

- Rainbow Eraser toggle under Color and Quality. Passes KCC's `--eraserainbow`, which attenuates the rainbow interference pattern colour e-ink screens add to colour pages. Off by default, and it only affects colour output.

Thanks to @Brandyii for the request (#10).

## v3.4.0: Folder Volumes, Format Cleanup & Watcher Fixes

The headline: drop a folder of images into `Comics_in` and it converts as a single bundled volume, a pile of long-standing conversion bugs are fixed, the image is 60% smaller, and the WebUI got a proper cleanup on desktop and mobile.

### Added

- Folder volumes: a folder of images dropped into `Comics_in` converts as one volume named after the folder, with subfolders as chapters. Folders containing comic archives convert file-by-file with structure preserved instead, since KCC can't ingest nested archives. Both work with Retry and Preserve Originals.

### Fixed

- Cropping was silently disabled for everyone: KCC expects a 0–1 ratio for cropping minimum but Bindery sent a percentage, so the old default of `1` blocked every crop. Values are now converted properly and the default is `0`.
- inotify mode never processed folder jobs (their events fire mid-copy) and could convert-and-delete files inside one individually. Folder contents now route to their folder job, and a 60 s backstop scan catches whatever events miss, including files on network mounts, which previously were missed entirely in inotify mode.
- The scanner walked into `<name>.failed` folders and converted the files inside, silently consuming a failed job's sources.
- Repeated failures no longer collide: `.failed` renames pick a free name, the job remembers the real path so Retry finds it, and Retry refuses to overwrite a newly dropped file with the same name.
- Jobs interrupted by a restart no longer sit as permanent "processing" rows.
- Files with dash-leading names (`-Batman.cbz`) failed inside KCC's 7z call; Bindery now renames them with a log line before converting.
- The live activity log froze once its 300-line buffer filled.
- Preserve Originals archive moves are collision-safe instead of overwriting files or nesting folders.

### Changed

- MOBI and KFX output removed: MOBI needs Amazon's abandoned kindlegen binary and KFX a Calibre plugin, neither of which can ship in this image, so every such conversion failed. Existing configs fall back to EPUB, which Kindles accept via [Send to Kindle](https://www.amazon.com/sendtokindle).
- KCC upgraded v9.4.3 → v10.3.0 (better PDF handling via rasterisation, five months of upstream fixes including the v10 major release) and installed without its GUI dependency chain; the image drops from 1.55 GB to about 620 MB.
- WebUI reworked: processing status, file browser, and activity log now sit above the settings form, text contrast fixed throughout, and the mobile layout no longer crushes the status table. Plus touch-sized buttons, keyboard focus outlines, and friendlier empty states.

## v3.3.1: Fix Startup Crash When SKIP_CHOWN Unset

### What's new

This is a bugfix release. `entrypoint.sh` crashed on startup with `SKIP_CHOWN: unbound variable` for any deployment that did not explicitly set the `SKIP_CHOWN` environment variable, which is the default for almost everyone. The script runs under `set -u`, and the `SKIP_CHOWN` check had no default, so the container exited before the app started.

`SKIP_CHOWN` now defaults to `false`, matching how `PUID` / `PGID` are already handled. Setting `SKIP_CHOWN=true` still behaves exactly as before.

### Changes

- Fixed: `entrypoint.sh` startup crash (`SKIP_CHOWN: unbound variable`) when `SKIP_CHOWN` is not set. It now defaults to `false`, consistent with the existing `PUID` / `PGID` pattern
- Note: behaviour is unchanged when `SKIP_CHOWN` is set explicitly

If you were affected, just pull the new image. No compose or config changes needed.

## v3.3.0: PDF Support for Comics

### What's new

Bindery now recognises `.pdf` as a comic input format. Drop a PDF into `Comics_in` alongside your `.cbz` / `.cbr` / `.zip` / `.rar` files and it gets picked up by both the poll scanner and the inotify watcher, then handed to KCC just like any other comic source.

A note on EPUBs since an issue mentioned them too: KCC does not accept EPUB as an input format (EPUB is one of its outputs). Graphic-novel EPUBs should go in `Books_in`, where they'll be handled by the kepubify pipeline. They won't get KCC's image-optimisation treatment, but that's a KCC limitation, not something Bindery can route around.

### Changes

- New: `.pdf` added to the comic input extension set, recognised by both poll-mode and inotify-mode watchers
- Note: EPUBs continue to be handled by the books pipeline via kepubify; KCC does not accept EPUB as input
- Added: unit test covering PDF dispatch in `scan_directories`

Existing setups need no changes. Drop a PDF in `Comics_in` and it just works. Thanks to @ponchohoncho for the report (#8).

## v3.2.0: Optional chown Skip

### What's new

By default, Bindery `chown`s its data folders on every container start so files end up owned by your `PUID`/`PGID`. That works everywhere a privileged container can write ownership, but on NFS shares mounted into unprivileged LXC containers the kernel blocks `chown` even when normal reads and writes work fine. The result was Bindery aborting at startup over a step it didn't strictly need.

This release adds a `SKIP_CHOWN` environment variable to opt out. Set it to `true` in your compose file and the chown step is bypassed entirely; Bindery trusts that whatever ownership the volumes already have is good enough.

### Changes

- New `SKIP_CHOWN` environment variable. Set to `true` to skip the initial `chown` step entirely
- Useful for NFS/SMB mounts in unprivileged LXC containers, or any setup where the container can read and write but not change ownership
- Default behaviour is unchanged: `chown` still runs unless `SKIP_CHOWN=true` is explicitly set

Disabled by default. Existing setups need no changes. Thanks to @ponchohoncho for the report (#7).

## v3.1.1: Skip Dot-Folders

### What's fixed

Syncthing (and similar sync tools) create hidden dot-folders inside watched directories: `.stfolder`, `.stversions`, etc. Bindery was scanning inside them and attempting to convert whatever files it found there.

### Changes

- Any directory whose name starts with `.` is now skipped universally in both poll and inotify modes. Covers `.stfolder`, `.stversions`, `.archive`, and anything else like them

No config changes needed. Existing setups will pick this up automatically on container restart.

## v3.1.0: Preserve Originals

### What's new

By default, Bindery deletes source files from `Comics_in` after a successful conversion. For most setups that's fine, but if you're running Bindery as part of a larger workflow and need the originals to stick around, there was no way to stop it.

This release adds a **Preserve Originals** toggle in Bindery Settings. When enabled, source comics are moved to `Comics_in/.archive` instead of deleted. The subfolder structure is mirrored: a file at `Comics_in/Marvel/issue01.cbz` archives to `Comics_in/.archive/Marvel/issue01.cbz`. The `.archive` folder is never scanned or reprocessed.

### Changes

- New **Preserve Originals** toggle in Bindery Settings. Moves source comics to `Comics_in/.archive` after conversion instead of deleting them
- `Comics_in/.archive` is excluded from both the poll scanner and the inotify watcher. Files there are never reprocessed

Disabled by default. No config changes needed for existing setups. Has no effect on book conversions.

## v3.0.2: Fix premature processing of in-progress file transfers

### What's fixed

Bindery was processing files that hadn't finished copying yet.

When dropping files into `/Comics_in` via FileBrowser, the file watcher would start a conversion before the transfer was complete. FileBrowser (and most copy tools) briefly pause between write chunks; if that pause hit Bindery's 2-second poll window, the file appeared stable when it wasn't. KCC then tried to convert a partial/corrupt CBZ, failed, and renamed it to `.failed`, which blocked FileBrowser from finishing the copy.

### Changes

- `wait_for_file_ready` now requires **3 consecutive stable size readings (~6 seconds)** instead of 1 before passing a file to the converter
- **inotify mode** now also handles `on_closed` (`IN_CLOSE_WRITE`), which fires only after the writing process fully closes the file, a definitive "transfer complete" signal for clients like FileBrowser

No config changes needed. Existing setups will pick this up automatically on container restart.

## v3.0.1: Bug Fixes & Housekeeping

### What's new

- Fixed: entrypoint.sh crashed on startup when PUID/PGID matched an existing system UID/GID
- Fixed: wait_for_file_ready waited up to 2s less than configured on odd timeout values
- Fixed: _notify used hardcoded fallback values instead of DEFAULT_CONFIG
- Improved: comic conversions now log STARTING when conversion begins, matching book log style
- Added: .dockerignore to reduce Docker build context
- Added: apprise to requirements-dev.txt so notification tests run in CI
- Added: 5 unit tests covering _notify paths

## v3.0.0: Status, File Browser & Notifications

### What's new

- Added: Processing Status card, a live table showing every conversion job with state, timestamps, duration, and a Retry button for failed files; history persists across restarts
- Added: File Browser card. Browse and download files from Books Out and Comics Out directly from the WebUI; no Samba or SSH required
- Added: Notifications via Apprise. Send push notifications on success and/or failure to ntfy, Discord, Slack, Telegram, Pushover, email, and 60+ other services
- Fixed: Save Configuration button moved below all settings cards so it clearly applies to both KCC and Bindery Settings

## v2.8.2: Inotify Initial Scan Fix

### What's new

- Fixed: inotify watcher mode did not scan existing files on startup: files already sitting in Comics_in, Books_in, or Comics_raw when the container started were silently ignored; an initial scan now runs before the observer starts

## v2.8.1: Bug Fixes & Project Structure

- Fixed: Dockerfile was hardcoding pip dependencies instead of installing from `requirements.txt`; now uses `COPY requirements.txt` + `pip install -r` for proper layer caching
- Fixed: CI workflow hardcoded `pip install flask pytest` instead of using `requirements-dev.txt`
- Fixed: `requirements-dev.txt` only contained `pytest`; added `flask` and `watchdog` so it reflects what tests actually need
- Added: `pyproject.toml` with project metadata and pytest configuration (`testpaths = ["tests"]`)

## v2.8.0: inotify Watcher Mode & WebUI Improvements

### What's new
- Added: inotify watcher mode, with instant file detection on local filesystems; poll remains the default and works everywhere including network shares (NFS, SMB)
- Added: Bindery Settings card in WebUI, with a Watcher Mode selector and File Stability Timeout field
- Added: Save & Restart button that saves settings and restarts the container in one step; the page auto-reloads when healthy
- Added: /api/restart endpoint
- Added: /api/logs endpoint, so the activity log live-polls every 5 s instead of requiring a page reload
- Added: persistent log at /app/config/bindery.log. It survives restarts and is pre-loaded into the UI on startup (trimmed to 5000 lines)
- Added: File Stability Timeout setting in WebUI (10–300 s, default 60)
- Fixed: kcc_borders, kcc_gamma, kcc_profile, kcc_format, kcc_cropping, kcc_splitter, and kcc_batchsplit were unvalidated; invalid POST values now fall back to safe defaults
- Fixed: kepubify pinned to v4.0.4 in Dockerfile; it was previously downloading latest at build time
- Improved: page subtitle reflects active watcher mode (polling vs inotify)
- Improved: SVG logo header replaces plain text title
- Added: 20 new tests covering _build_kcc_cmd, process_file error paths, scan_directories, _validate_post, and /api/logs

## v2.7.1: WebUI Polish

- Fixed: reMarkable device profiles now use a Jinja for loop, consistent with Kindle and Kobo
- Fixed: log section h2 used inline styles to fight its own class rules; replaced with `.log-title` modifier class
- Fixed: version line used a fragile negative margin; now a proper `.version` class in natural document flow
- Fixed: Output Metadata checks div used an inline `margin-bottom`; replaced with `.checks-spaced` class
- Improved: Custom Profile Resolution fields (width, height, note) are now hidden unless Generic / Custom profile is selected
- Improved: KCC log no longer emits a redundant STARTING line before QUEUED; comics now log QUEUED then CMD

## v2.7.0: Device Profiles & Borders Overhaul
- Fixed: incorrect KCC profile keys that were silently passing wrong values: `K578` split into correct `K57` (Kindle 5/7) and `K810` (Kindle 8/10); `KPW3` corrected to `KPW34`; `KoM`+`KoT` merged to correct `KoMT` (Kobo Mini/Touch); `KoCE` corrected to `KoCC` (Kobo Clara Colour); removed `KoE2` (no KCC profile exists)
- Added missing KCC profiles: `K11` (Kindle 11), `KCS` (Kindle Colorsoft), `KS3` (Kindle Scribe 3), `KSCS` (Kindle Scribe Colorsoft), `KS1860`, `KS1920`, `KoN` (Kobo Nia), `KoS` (Kobo Sage), `RmkPPMove` (reMarkable Paper Pro Move)
- Updated `KO` label to include Paperwhite 12; updated `KS` label to Scribe 1/2
- Changed: Borders setting replaced two checkboxes (Black Borders / White Borders) with a single dropdown (None / Black / White)
- Note: existing `settings.json` files will get the new `kcc_borders` key defaulting to `black` on next save

## v2.6.0: Housekeeping
- Added `requirements.txt` listing production dependencies (Flask, gunicorn, packaging, kcc)
- Fixed: `comics_raw/` added to `.gitignore` to prevent accidentally tracking dropped image files
- Fixed: `test_processor.py` mock config now imports directly from `config.py` instead of using a stale hardcoded fallback dict
- Refactored: `app.py` now uses a `create_app()` factory; background threads no longer start at import time, removing the need for the import-time `threading.Thread` patch in `conftest.py`
- Refactored: `_build_kcc_cmd` extracted from `process_file` in `processor.py`; KCC argument building is now a standalone testable function
- Added module docstrings to all Python modules
- Added docstrings to previously undocumented functions
- Added type hints to all function signatures across `app.py`, `config.py`, `processor.py`, and `raw_processor.py`
- Added `ConfigDict` type alias in `config.py` for the shared settings dictionary type

## v2.5.0: Bug Fixes

- Fixed: gunicorn "Control server error: Permission denied" on every container start; disabled the unused control socket introduced in gunicorn 25.1.0
- Fixed: files that convert successfully but produce no output were retried on every scan instead of being flagged `.failed`
- Fixed: unexpected exceptions in `process_file` (e.g. permission errors, disk full) left the source file untouched and retried forever; now renamed `.failed` same as other failure paths
- Fixed: raw folders that hit an unexpected error during zipping were left in `Comics_raw` and retried forever; they are now moved to `Comics_raw/unprocessed/` like other failures
- Fixed: subdirectory path calculation for files in the root of `Comics_in` / `Books_in` used the wrong `os.path` call order (worked by accident; now correct)
- Fixed: `load_config` and `save_config` had no locking; concurrent conversion threads reading config while a POST was writing it could get partial JSON and silently fall back to defaults
- Fixed: `settings.json` could be left truncated if the process was killed mid-write; write is now atomic via temp file + `os.replace()`
- Fixed: WebUI accepted non-numeric input for `croppingpower`, `croppingminimum`, `customwidth`, and `customheight`; values are now validated and clamped before saving
- Improved: `entrypoint.sh` `chown` no longer walks every file in all volumes on every container start; only files not already owned by `abc` are touched
- Added comment to `wait_for_file_ready` explaining the 60s timeout and why SKIP does not rename to `.failed`
- Added warning comment in `app.py` explaining why `--preload` must not be added to gunicorn

## v2.4.0: Docker Hub Image

- Bindery is now available as a pre-built image at `dinkeyes/bindery` on Docker Hub, no clone or build step required
- Added GitHub Actions workflow to automatically build and push images on each release
- Updated README with Docker Hub quick start and updated compose example

Versions before 2.4.0 predate this changelog.
