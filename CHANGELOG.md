## v4.3.2: Source-Built kepubify

The Docker image now builds kepubify from its pinned source instead of downloading a binary compiled with an older Go toolchain.

### Changed

- **kepubify is built from source**: the image compiles kepubify 4.0.4 from its pinned upstream commit with Go 1.26.5 and updated direct dependencies. Book conversion stays on kepubify 4.0.4; this changes how the binary is built, not its settings or output options.

### Upgrading

Pull the latest image and restart. Settings and conversion behaviour are unchanged.

## v4.3.1: Settings Save Fix

A fix for the Books settings card added in v4.3.0, which could drop the rest of your settings when it refused an output extension.

### Fixed

- **A blocked book extension no longer discards the rest of the page**: with `Books_in` and `Books_out` overlapping, choosing `.epub` or `.kepub.epub` refused the whole save, so anything else changed at the same time went with it: KCC author, custom CSS, notification URLs, watcher mode. The page then redisplayed those values as though they had been saved. Bindery now keeps the output extension it already had, saves everything else, and says which extension it kept and why.

### Upgrading

Pull the latest image and restart. Settings are unchanged.

## v4.3.0: Books Settings & KCC 11

Books now have their own conversion controls, with safer output naming and an updated conversion stack.

### Added

- **Books settings card**: everything dropped into `Books_in` now has its own settings card in the WebUI, exposing kepubify's conversion options: output extension, smarten punctuation, hyphenation, dummy titlepage, fullscreen reading fixes, custom CSS, find and replace, and charset override. Previously every one of these was hardcoded.
- **Output extension for books**: choose `.kepub`, the default and what Calibre and Calibre-Web-Automated expect, `.kepub.epub`, what a Kobo recognises over USB, or `.epub` for a conventional filename. All three options still run the book through kepubify and contain Kobo enhancements.

### Fixed

- **No KEPUB Extension no longer looks like it applies to books**: the setting is a KCC option and only ever affected comics, but nothing in the UI said so, so ticking it and dropping an EPUB into `Books_in` looked like a bug. It is now labelled as comics only, and books have their own extension setting.
- **Overlapping book folders fail safely**: converted `.epub` and `.kepub.epub` files can be picked up as fresh input when either book folder contains the other. Bindery now rejects every overlapping layout in the WebUI and pauses book processing if it finds one in a hand-edited config, leaving source files untouched instead of converting them repeatedly.
- **KCC settings match KCC 11**: the landscape splitter now shows KCC's real Split, Rotate, and Split and rotate modes; obsolete controls that made conversions fail are gone; and KCC's current spread options and Kindle Paperwhite and Scribe profiles are available.

### Changed

- **Python 3.13 and KCC 11.0.1**: the Docker image now runs both, with current runtime libraries and GitHub Actions. Existing saved KCC settings are migrated to the supported equivalents automatically.

Thanks to @tekgnosis-net for contributing the books settings work in #14.

### Upgrading

Pull the latest image and restart. Existing settings keep the old `.kepub` behaviour by default. Before choosing `.epub` or `.kepub.epub`, make sure `Books_in` and `Books_out` are separate folders and neither one contains the other.

## v4.2.1: Keep-in-Place Fixes

Two bugs surfaced by the follow-up on issue #13, both hitting libraries where `Comics_in` and `Comics_out` share a folder with a library manager.

### Fixed

- **A timestamp touch no longer re-converts a kept source**: library managers touch files when they scan or rewrite metadata, and Bindery counted every touch as a new version, converting the same comic over and over and adding a `_2`, `_3`... copy each round. A kept source now re-converts only when its content actually changes, and when it does the new book replaces the earlier one instead of stacking another copy beside it.
- **Folders without comics are left alone**: a top-level folder in `Comics_in` holding nothing comic-typed, an epub-only book folder in a shared library for instance, was treated as a folder conversion job, failed inside KCC, and got the whole folder renamed to `<name>.failed`. Folders with nothing to convert are no longer jobs and are never renamed.

### Upgrading

Pull the latest image and restart. Leftover `_2`, `_3`... copies from the loop are safe to delete. If any folder in your library picked up a `.failed` suffix from the second bug, rename it back and it will be left alone from now on.

## v4.2.0: Light Mode, Dashboards & ComicInfo

Three additions aimed at making Bindery nicer to live with and easier to keep an eye on.

### Added

- **Light theme**: the WebUI now follows your system's light or dark setting, with a toggle in the header that remembers your choice. The activity log keeps its terminal look in both.
- **`/api/stats` for dashboards**: a small JSON endpoint reporting lifetime conversions, space saved, and the live queue, ready for a [Homepage](https://gethomepage.dev/) widget or an Uptime Kuma monitor. Setup is in the README.
- **Use ComicInfo.xml metadata**: turn it on in the KCC settings and Bindery reads the series, number, and title from a comic's embedded `ComicInfo.xml`, so a file named `Chapter 1 (2).cbz` still arrives on your reader as *Berserk #001: The Black Swordsman*. Off by default; falls back to the filename when there's no metadata.

### Note

- **The image is multi-arch and always has been**, x86 and ARM64 both, so a Raspberry Pi or ARM NAS works too. This is now called out in the README.

## v4.1.0: Keep Originals In Place

A small release for anyone who keeps their comics in a library manager: leave the source file exactly where it is.

### Added

- **Keep in place**: the Originals setting has a new option that leaves a source comic right where it is after it converts, instead of deleting it or moving it to `.archive`. Point `Comics_in` and `Comics_out` at the same folder and the original and the converted book end up side by side, which is what tools like Calibre, Kavita, and BookOrbit expect. Bindery keeps a small record of what it has already converted, so a kept source is never re-converted on the next scan, and re-converts on its own only if you drop a changed copy over it.

### Changed

- **Preserve Originals is now a three-way Originals setting**: Delete after converting (the default), Move to `Comics_in/.archive`, or Keep in place. Existing settings migrate automatically, so nothing changes unless you pick the new option.

Thanks to @thevanburenboy for the clear write-up in #13.

## v4.0.0: Device Profiles, Browser Upload & Merged Volumes

Per-device conversion settings with their own drop folders, uploads straight from the browser, and chapter folders that bundle into one volume.

### Added

- **Device Profiles**: create named profiles in the WebUI (`kobo`, `kindle`, ...), each with its own KCC settings and its own drop folder. `Comics_in/kobo` converts for the Kobo and lands in `Comics_out/kobo`; `Comics_in/kindle` for the Kindle. Drops in the root of `Comics_in` behave exactly as they always have, and nothing changes until you create your first profile.
- **Upload from the browser**: drag files onto the WebUI, or tap the strip on a phone, and they land in the right watch folder, including profile folders. No network shares or shell access needed.
- **Bundle Chapter Folders**: turn it on and a folder of chapter archives (`.cbz`/`.cbr`/`.zip`/`.rar`) converts as ONE volume with a chapter per file in natural order, instead of one book per chapter. Off by default; per-file conversion stays the default behaviour. Folders of chapter files now bundle properly, not just folders of images.
- **Size savings**: successful conversions show before → after sizes and the percentage saved in the status table.

### Changed

- **WebUI**: a full visual refresh.
- **KCC upgraded `v10.3.0` → `v10.4.0`**: a smart-cover-crop crash fix and higher JPEG quality on Scribe and Colorsoft profiles.

Thanks to @Elrict for pushing on chapter bundling back in #9.

## v3.6.0: MozJPEG

KCC's MozJPEG option is now a toggle in the WebUI. Turn it on and the JPEG pages inside the output book are re-encoded with the MozJPEG encoder for smaller files, at the cost of somewhat slower conversion.

### Added

- **MozJPEG**: a toggle under Color and Quality. It passes KCC's `--mozjpeg`, which re-encodes every JPEG page with the MozJPEG encoder. Off by default since it slows processing.

Thanks to @Brandyii for the suggestion (#11).

## v3.5.0: Rainbow Eraser

KCC's rainbow eraser is now a toggle in the WebUI. Turn it on and colour pages get the interference pattern that colour e-ink screens introduce attenuated on the way through, the same option KCC exposes for devices like the Kindle Colorsoft and Kobo Libra Colour.

### Added

- **Rainbow Eraser**: a toggle under Color and Quality. It passes KCC's `--eraserainbow`, which attenuates the rainbow interference pattern colour e-ink screens add to colour pages. Off by default, and it only affects colour output.

Thanks to @Brandyii for the request (#10).

## v3.4.0: Folder Volumes, Format Cleanup & Watcher Fixes

Drop a folder of images into `Comics_in` and it converts as a single bundled volume, a pile of long-standing conversion bugs are fixed, the image is 60% smaller, and the WebUI got a proper cleanup on desktop and mobile.

### Added

- **Folder volumes**: a folder of images dropped into `Comics_in` converts as one volume named after the folder, with subfolders as chapters. Folders containing comic archives convert file-by-file with structure preserved instead, since KCC cannot ingest nested archives. Both work with Retry and Preserve Originals.

### Fixed

- **Cropping was silently disabled for everyone**: KCC expects a 0-1 ratio for cropping minimum but Bindery sent a percentage, so the old default of `1` blocked every crop. Values are now converted properly and the default is `0`.
- **inotify mode never processed folder jobs**: their events fire mid-copy, and it could convert and delete files inside a folder individually. Folder contents now route to their folder job, and a 60 s backstop scan catches whatever events miss, including files on network mounts, which were previously missed entirely in inotify mode.
- **`.failed` folders were scanned**: the scanner walked into `<name>.failed` folders and converted the files inside, silently consuming a failed job's sources.
- **Repeated failures no longer collide**: `.failed` renames pick a free name, the job remembers the real path so Retry finds it, and Retry refuses to overwrite a newly dropped file with the same name.
- **Interrupted jobs**: jobs interrupted by a restart no longer sit as permanent "processing" rows.
- **Dash-leading filenames**: files like `-Batman.cbz` failed inside KCC's 7z call. Bindery now renames them with a log line before converting.
- **Activity log freeze**: the live log froze once its 300-line buffer filled.
- **Archive moves**: Preserve Originals archive moves are collision-safe instead of overwriting files or nesting folders.

### Changed

- **MOBI and KFX output removed**: MOBI needs Amazon's abandoned kindlegen binary and KFX needs a Calibre plugin, neither of which can ship in this image, so every such conversion failed. Existing configs fall back to EPUB, which Kindles accept via [Send to Kindle](https://www.amazon.com/sendtokindle).
- **KCC upgraded v9.4.3 → v10.3.0**: better PDF handling via rasterisation and five months of upstream fixes, including the v10 major release. It installs without its GUI dependency chain, dropping the image from 1.55 GB to about 620 MB.
- **WebUI reworked**: processing status, file browser, and activity log now sit above the settings form, text contrast is fixed throughout, and the mobile layout no longer crushes the status table. Plus touch-sized buttons, keyboard focus outlines, and friendlier empty states.

## v3.3.1: Fix Startup Crash When SKIP_CHOWN Unset

A bugfix release. `entrypoint.sh` crashed on startup for any deployment that did not explicitly set the `SKIP_CHOWN` environment variable, which is the default for almost everyone.

### Fixed

- **`SKIP_CHOWN: unbound variable` on startup**: the script runs under `set -u` and the `SKIP_CHOWN` check had no default, so the container exited before the app started. `SKIP_CHOWN` now defaults to `false`, matching how `PUID` and `PGID` are already handled. Setting `SKIP_CHOWN=true` still behaves exactly as before.

### Upgrading

If you were affected, pull the new image. No compose or config changes are needed.

## v3.3.0: PDF Support for Comics

Bindery now recognises `.pdf` as a comic input format.

### Added

- **`.pdf` comic input**: drop a PDF into `Comics_in` alongside your `.cbz`, `.cbr`, `.zip`, and `.rar` files and it gets picked up by both the poll scanner and the inotify watcher, then handed to KCC just like any other comic source.
- **Test coverage**: a unit test covering PDF dispatch in `scan_directories`.

### Note

- **EPUBs are still handled by the books pipeline**: KCC does not accept EPUB as an input format, since EPUB is one of its outputs. Graphic-novel EPUBs should go in `Books_in`, where kepubify handles them. They will not get KCC's image-optimisation treatment, but that is a KCC limitation rather than something Bindery can route around.

Thanks to @ponchohoncho for the report (#8).

### Upgrading

Pull the latest image and restart. Existing setups need no changes; drop a PDF in `Comics_in` and it just works.

## v3.2.0: Optional chown Skip

Bindery `chown`s its data folders on every container start so files end up owned by your `PUID`/`PGID`. On NFS shares mounted into unprivileged LXC containers the kernel blocks that even though normal reads and writes work fine, so Bindery aborted at startup over a step it did not strictly need.

### Added

- **`SKIP_CHOWN` environment variable**: set it to `true` in your compose file and the initial `chown` step is bypassed entirely, with Bindery trusting whatever ownership the volumes already have. Useful for NFS and SMB mounts in unprivileged LXC containers, or any setup where the container can read and write but not change ownership.

Thanks to @ponchohoncho for the report (#7).

### Upgrading

Pull the latest image and restart. Default behaviour is unchanged; `chown` still runs unless `SKIP_CHOWN=true` is set explicitly.

## v3.1.1: Skip Dot-Folders

Syncthing and similar sync tools create hidden dot-folders inside watched directories, and Bindery was scanning inside them and converting whatever it found.

### Fixed

- **Dot-folders are skipped**: any directory whose name starts with `.` is now skipped in both poll and inotify modes. That covers `.stfolder`, `.stversions`, `.archive`, and anything else like them.

### Upgrading

Pull the latest image and restart. No config changes are needed.

## v3.1.0: Preserve Originals

By default Bindery deletes source files from `Comics_in` after a successful conversion. For most setups that is fine, but if you run Bindery as part of a larger workflow and need the originals to stick around, there was no way to stop it.

### Added

- **Preserve Originals**: a toggle in Bindery Settings. With it on, source comics move to `Comics_in/.archive` instead of being deleted, and the subfolder structure is mirrored, so a file at `Comics_in/Marvel/issue01.cbz` archives to `Comics_in/.archive/Marvel/issue01.cbz`. `Comics_in/.archive` is excluded from both the poll scanner and the inotify watcher, so files there are never reprocessed.

### Upgrading

Pull the latest image and restart. The toggle is off by default, existing setups need no changes, and book conversions are unaffected.

## v3.0.2: Fix Premature Processing of In-Progress File Transfers

Bindery was converting files that had not finished copying yet.

### Fixed

- **Partial transfers are no longer converted**: when dropping files into `Comics_in` via FileBrowser, the watcher could start a conversion before the transfer finished. FileBrowser, like most copy tools, pauses briefly between write chunks, and if that pause hit Bindery's 2-second poll window the file looked stable when it was not. KCC then tried to convert a partial or corrupt CBZ, failed, and renamed it to `.failed`, which blocked FileBrowser from finishing the copy. `wait_for_file_ready` now requires 3 consecutive stable size readings, about 6 seconds, instead of 1 before handing a file to the converter.
- **inotify close events**: inotify mode also handles `on_closed` (`IN_CLOSE_WRITE`), which fires only once the writing process has fully closed the file, a definitive transfer-complete signal for clients like FileBrowser.

### Upgrading

Pull the latest image and restart. No config changes are needed.

## v3.0.1: Bug Fixes & Housekeeping

A round of small fixes and build cleanup.

### Added

- **`.dockerignore`**: reduces the Docker build context.
- **apprise in `requirements-dev.txt`**: so the notification tests run in CI.
- **Test coverage**: 5 unit tests covering `_notify` paths.

### Fixed

- **Startup crash**: `entrypoint.sh` crashed when PUID/PGID matched an existing system UID/GID.
- **File stability timeout**: `wait_for_file_ready` waited up to 2 s less than configured on odd timeout values.
- **Notification defaults**: `_notify` used hardcoded fallback values instead of `DEFAULT_CONFIG`.

### Changed

- **Comic logging**: comic conversions now log STARTING when conversion begins, matching the book log style.

## v3.0.0: Status, File Browser & Notifications

Three additions that make it possible to see what Bindery is doing without opening a shell.

### Added

- **Processing Status card**: a live table showing every conversion job with state, timestamps, duration, and a Retry button for failed files. History persists across restarts.
- **File Browser card**: browse and download files from Books Out and Comics Out directly from the WebUI, with no Samba or SSH needed.
- **Notifications via Apprise**: send push notifications on success and/or failure to ntfy, Discord, Slack, Telegram, Pushover, email, and 60+ other services.

### Fixed

- **Save Configuration placement**: the button now sits below all settings cards, so it is clear that it applies to both KCC and Bindery Settings.

## v2.8.2: Inotify Initial Scan Fix

A fix for inotify mode, which ignored files that were already waiting when the container started.

### Fixed

- **Existing files are picked up on startup**: files already sitting in `Comics_in`, `Books_in`, or `Comics_raw` when the container started were silently ignored in inotify mode. An initial scan now runs before the observer starts.

## v2.8.1: Bug Fixes & Project Structure

Build and dependency cleanup.

### Added

- **`pyproject.toml`**: project metadata and pytest configuration (`testpaths = ["tests"]`).

### Fixed

- **Dockerfile dependencies**: it hardcoded pip dependencies instead of installing from `requirements.txt`. It now uses `COPY requirements.txt` and `pip install -r` for proper layer caching.
- **CI dependencies**: the workflow hardcoded `pip install flask pytest` instead of using `requirements-dev.txt`.
- **`requirements-dev.txt`**: it only contained `pytest`, so `flask` and `watchdog` are added and it now reflects what the tests actually need.

## v2.8.0: inotify Watcher Mode & WebUI Improvements

Instant file detection on local filesystems, a settings card in the WebUI, and a live activity log.

### Added

- **inotify watcher mode**: instant file detection on local filesystems. Poll remains the default and works everywhere, including network shares (NFS, SMB).
- **Bindery Settings card**: a WebUI card with a Watcher Mode selector and a File Stability Timeout field (10-300 s, default 60).
- **Save & Restart**: saves settings and restarts the container in one step, and the page reloads itself once the container is healthy.
- **`/api/restart` and `/api/logs` endpoints**: the activity log live-polls every 5 s instead of needing a page reload.
- **Persistent log at `/app/config/bindery.log`**: it survives restarts and is pre-loaded into the UI on startup, trimmed to 5000 lines.
- **Test coverage**: 20 new tests covering `_build_kcc_cmd`, `process_file` error paths, `scan_directories`, `_validate_post`, and `/api/logs`.

### Fixed

- **Unvalidated settings**: `kcc_borders`, `kcc_gamma`, `kcc_profile`, `kcc_format`, `kcc_cropping`, `kcc_splitter`, and `kcc_batchsplit` accepted anything. Invalid POST values now fall back to safe defaults.
- **kepubify version drift**: kepubify is pinned to v4.0.4 in the Dockerfile instead of downloading the latest at build time.

### Changed

- **Page subtitle**: it reflects the active watcher mode, polling or inotify.
- **Header**: an SVG logo replaces the plain text title.

## v2.7.1: WebUI Polish

A round of WebUI and stylesheet cleanup.

### Fixed

- **reMarkable device profiles**: they now use a Jinja for loop, consistent with Kindle and Kobo.
- **Log section heading**: it used inline styles to fight its own class rules, and now uses a `.log-title` modifier class.
- **Version line**: it used a fragile negative margin, and is now a `.version` class in natural document flow.
- **Output Metadata spacing**: the checks div used an inline `margin-bottom`, and now uses a `.checks-spaced` class.

### Changed

- **Custom Profile Resolution fields**: width, height, and note are hidden unless the Generic or Custom profile is selected.
- **KCC logging**: no redundant STARTING line before QUEUED; comics log QUEUED, then CMD.

## v2.7.0: Device Profiles & Borders Overhaul

A pass over the KCC device profile list, which had several keys that silently sent the wrong values, plus a simpler Borders control.

### Added

- **Missing KCC profiles**: `K11` (Kindle 11), `KCS` (Kindle Colorsoft), `KS3` (Kindle Scribe 3), `KSCS` (Kindle Scribe Colorsoft), `KS1860`, `KS1920`, `KoN` (Kobo Nia), `KoS` (Kobo Sage), and `RmkPPMove` (reMarkable Paper Pro Move).

### Fixed

- **Profile keys that silently passed wrong values**: `K578` is split into `K57` (Kindle 5/7) and `K810` (Kindle 8/10); `KPW3` is corrected to `KPW34` (Paperwhite 3/4); `KoM` and `KoT` are merged into `KoMT` (Kobo Mini/Touch); `KoCE` is corrected to `KoCC` (Kobo Clara Colour); and `KoE2` is removed, since no KCC profile exists for it.
- **Profile labels**: `KO` now includes Paperwhite 12, and `KS` reads Scribe 1/2.

### Changed

- **Borders**: the two Black Borders and White Borders checkboxes are now a single dropdown with None, Black, and White.

### Upgrading

Existing `settings.json` files pick up the new `kcc_borders` key, defaulting to `black`, on the next save.

## v2.6.0: Housekeeping

Internal cleanup with no user-facing changes.

### Added

- **`requirements.txt`**: production dependencies are listed explicitly (Flask, gunicorn, packaging, kcc).
- **`ConfigDict` type alias**: in `config.py`, for the shared settings dictionary type.
- **Docstrings and type hints**: module docstrings on every Python module, docstrings on previously undocumented functions, and type hints across `app.py`, `config.py`, `processor.py`, and `raw_processor.py`.

### Fixed

- **`comics_raw/` was trackable**: it is now in `.gitignore`, so dropped image files cannot be committed by accident.
- **Stale test config**: `test_processor.py` builds its mock config from `config.py` instead of a hardcoded fallback dict.

### Changed

- **`create_app()` factory**: `app.py` uses one, so background threads no longer start at import time and `conftest.py` no longer needs its import-time `threading.Thread` patch.
- **`_build_kcc_cmd` extracted**: KCC argument building is a standalone testable function in `processor.py` rather than part of `process_file`.

## v2.5.0: Bug Fixes

A batch of failure-path fixes, mostly around files that could retry forever.

### Fixed

- **gunicorn control socket**: "Control server error: Permission denied" on every container start. The unused control socket introduced in gunicorn 25.1.0 is disabled.
- **Successful conversions that produce no output**: they were retried on every scan instead of being flagged `.failed`.
- **Unexpected exceptions in `process_file`**: permission errors, a full disk and the like left the source file untouched and retrying forever. They are now renamed `.failed` like other failure paths.
- **Raw folders that error while zipping**: they were left in `Comics_raw` and retried forever, and now move to `Comics_raw/unprocessed/` like other failures.
- **Subdirectory paths for root-level files**: files in the root of `Comics_in` or `Books_in` used the wrong `os.path` call order. It worked by accident; it is now correct.
- **Unlocked config reads and writes**: `load_config` and `save_config` had no locking, so a conversion thread reading config while a POST was writing it could get partial JSON and silently fall back to defaults.
- **Truncated `settings.json`**: it could be left half-written if the process was killed mid-write. Writes are now atomic via a temp file and `os.replace()`.
- **Non-numeric WebUI input**: `croppingpower`, `croppingminimum`, `customwidth`, and `customheight` accepted anything. Values are validated and clamped before saving.

### Changed

- **`entrypoint.sh` chown**: it no longer walks every file in every volume on each container start; only files not already owned by `abc` are touched.
- **Code comments**: `wait_for_file_ready` explains the 60 s timeout and why SKIP does not rename to `.failed`, and `app.py` explains why `--preload` must not be added to gunicorn.

## v2.4.0: Docker Hub Image

Bindery now ships as a pre-built image, so there is no clone or build step.

### Added

- **Docker Hub image**: Bindery is available as a pre-built image at `dinkeyes/bindery`.
- **Release build workflow**: a GitHub Actions workflow builds and pushes images automatically on each release.

### Changed

- **README**: the quick start now covers Docker Hub, with an updated compose example.

Versions before 2.4.0 predate this changelog.
