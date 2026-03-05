# ![Bindery](assets/logo.png)

[![Tests](https://github.com/jarynclouatre/bindery/actions/workflows/test.yml/badge.svg)](https://github.com/jarynclouatre/bindery/actions/workflows/test.yml)

A self-hosted, Dockerized converter that automatically processes e-books and comics dropped into watched folders — no manual steps required.

**For Kobo users:** Converts `.epub` files to Kobo's native `.kepub` format using [kepubify](https://github.com/pgaskin/kepubify), giving you better performance and reading features than sideloaded EPUBs.

**For all devices:** Converts comic archives (`.cbz`, `.cbr`, `.zip`, `.rar`) into device-optimised files using [Kindle Comic Converter (KCC)](https://github.com/ciromattia/kcc), with full control over profile, cropping, splitting, gamma, and more.

All settings are configurable at runtime via a WebUI on port 5000 — no container rebuild needed. Supports `PUID`/`PGID` permission mapping for NAS and multi-user environments. Failed files are flagged and skipped rather than retried in a loop.

**Supported devices:** Kindle, Kobo, reMarkable, and any device KCC has a profile for.


![Bindery WebUI](assets/webui.png)

### Use Cases

Bindery fits anywhere in a self-hosted media pipeline. Point the output folders at whatever consumes your files:

- **[Calibre-Web Automated](https://github.com/crocodilestick/Calibre-Web-Automated)** — set `books_out` as the CWA ingest folder and converted `.kepub` files are imported to your library automatically
- **[Calibre](https://calibre-ebook.com/) auto-add** — point Calibre's Auto Add folder at `books_out` or `comics_out` for hands-free import
- **Cloud sync** — use rclone to push converted files to Google Drive, Dropbox, or any cloud storage automatically (see [rclone setup](#rclone-auto-sync) below)

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/jarynclouatre/bindery
cd bindery

# 2. Find your user/group IDs
id
# → uid=1000(you) gid=1000(you)

# 3. Set PUID/PGID in docker-compose.yml, then start
docker compose up -d --build

# 4. Open the WebUI
http://<server-ip>:5000
```

---

## Folder Layout

```
bindery/
├── books_in/        ← drop .epub ├── books_in/        ← drop .epub files here (Kobo users only)
├── books_out/       ← converted .kepub files appear here
├── comics_in/       ← drop .cbz / .cbr / .zip / .rar here
├── comics_out/      ← converted files appear here
├── comics_raw/      ← drop a flat folder of images here; Bindery zips it to CBZ and processes it automatically
│   ├── processed/   ← original image folders moved here on success
│   └── unprocessed/ ← folders with subfolders or no images moved here
└── config/          ← settings.json persisted here
```

All four folders are created automatically on first run. Subfolders are preserved — a file at `comics_in/Marvel/issue01.cbz` will land at `comics_out/Marvel/issue01.kepub`.

---

## docker-compose.yml

Adjust the volume paths if your media lives somewhere other than the repo directory.

```yaml
services:
  bindery:
    build: .
    container_name: bindery
    ports:
      - "5000:5000"
    environment:
      - PUID=1000   # replace with your uid
      - PGID=1000   # replace with your gid
    volumes:
      - ./config:/app/config
      - /path/to/books_in:/Books_in
      - /path/to/books_out:/Books_out
      - /path/to/comics_in:/Comics_in
      - /path/to/comics_out:/Comics_out
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## KCC Settings

### Device and Output

| Setting | Default | Notes |
|---------|---------|-------|
| Device Profile | `KoLC` (Kobo Libra Colour) | Match your exact device for correct resolution |
| Output Format | `EPUB` | Kobo uses EPUB; Kindle prefers MOBI |
| Batch Split | `Disabled` | Split input into volumes or chapters |

### Image Processing

| Setting | Default | Notes |
|---------|---------|-------|
| Cropping | `2` (Margins + page numbers) | Removes white borders and page numbers |
| Cropping Power | `1.0` | Aggressiveness of the crop; higher = more aggressive |
| Cropping Minimum | `1%` | Minimum percentage to crop before cropping is skipped |
| Splitter | `1` (Left then right) | How landscape pages are split; use `2` (Right then left) for manga |
| Gamma | `Auto` | Brightness correction; leave on Auto unless your device needs tuning |

### Page Layout

| Setting | Default | Notes |
|---------|---------|-------|
| Manga Style | off | Enables right-to-left page navigation order |
| Two Panel | off | Treats landscape pages as two-panel spreads |
| Webtoon | off | Optimises for vertical-strip webtoon format |
| Stretch | **on** | Fills the screen, ignoring the original aspect ratio |
| Upscale | off | Upscales images smaller than the device resolution |
| No Split / Rotate | off | Disables splitting of landscape pages entirely (overrides splitter)|
| Rotate | off | Rotates landscape pages instead of splitting them (overrides splitter) |

Note: Some Page Layout settings have priority over others. For example, enabling No Split / Rotate will override the Splitter settings to ensure landscape pages remain as single images.

### Borders

| Setting | Default | Notes |
|---------|---------|-------|
| Black Borders | **on** | Fills unused screen area with black |
| White Borders | off | Fills unused screen area with white (overrides black borders) |

### Color and Quality

| Setting | Default | Notes |
|---------|---------|-------|
| Force Color | **on** | Preserves color data even on grayscale device profiles |
| Auto-Contrast | **on** | Automatically boosts color image contrast |
| Color Curve | off | Applies S-curve color correction to images |
| High Quality | off | Slower processing, marginally better image output |

### Output Metadata

| Setting | Default | Notes |
|---------|---------|-------|
| Use Filename as Title | **on** | Sets EPUB metadata title from the source filename |
| No KEPUB Extension | off | Outputs `.epub` instead of `.kepub` on Kobo profiles (KCC outputs `.kepub.epub` by default, which Bindery renames to `.kepub`) |
| Author | *(blank)* | Embeds an author name in EPUB metadata; leave blank to use KCC's default |

### Custom Profile Resolution

Only used when the Device Profile is set to **Generic / Custom**.

| Setting | Default | Notes |
|---------|---------|-------|
| Custom Width (px) | *(blank)* | e.g. `1264` |
| Custom Height (px) | *(blank)* | e.g. `1680` |

---

## Behaviour

- The scanner polls `/Books_in` and `/Comics_in` every **10 seconds** (polling is used over inotify to ensure compatibility with NAS network drives).
- Each file gets a per-file lock so the same file is never processed twice concurrently.
- On success: converted file is moved to the output folder, source file is deleted.
- On failure: source file is renamed to `<filename>.failed` so it is not retried in a loop.
- Raw folders in Comics_raw are held until stable (no file changes for 30 seconds) before processing begins, to avoid zipping a mid-transfer folder.
- Live logs are shown in the WebUI and streamed to `docker logs`.

---

## rclone Auto-Sync

You can have rclone watch the output folders and push converted files to cloud storage automatically. This example syncs `comics_out` to Google Drive.

### 1. Install rclone

```bash
sudo apt install rclone
```

### 2. Configure a remote

```bash
rclone config
```

Follow the interactive prompts to add a remote. Name it something like `gdrive`. Full instructions for each provider are at [rclone.org/docs](https://rclone.org/docs/).

### 3. Test manually

```bash
rclone copy /path/to/bindery/comics_out gdrive:Comics --progress
```

### 4. Run on a schedule with cron

```bash
crontab -e
```

Add a line to sync every 15 minutes:

```
*/15 * * * * rclone sync /path/to/bindery/comics_out gdrive:Comics --log-file=/var/log/rclone-comics.log
*/15 * * * * rclone sync /path/to/bindery/books_out gdrive:Books --log-file=/var/log/rclone-books.log
```

### 5. Or run as a systemd service for real-time sync

Create `/etc/systemd/system/rclone-bindery.service`:

```ini
[Unit]
Description=rclone sync Bindery output to cloud
After=network-online.target

[Service]
Type=simple
ExecStart=rclone sync /path/to/bindery/comics_out gdrive:Comics --log-file=/var/log/rclone-bindery.log
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now rclone-bindery
```

---

## Updating

```bash
cd /path/to/bindery && git pull && docker compose up -d --build
```
