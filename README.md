# E-Reader Converter

Automated, Dockerized converter for e-books and comics. Drop files into watched folders and pick them up on your device — no manual steps required.

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| **kepubify** | EPUB → Kobo format | `/Books_in` | `/Books_out` (`.kepub`) |
| **KCC** | CBZ/CBR → device-optimised comic | `/Comics_in` | `/Comics_out` |

A WebUI on port **5000** lets you configure the device profile and all conversion options at runtime without rebuilding the container.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/jarynclouatre/ereader-converter
cd ereader-converter

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
ereader-converter/
├── books_in/        ← drop .epub / .kepub here
├── books_out/       ← converted .kepub files appear here
├── comics_in/       ← drop .cbz / .cbr / .zip / .rar here
├── comics_out/      ← converted files appear here
└── config/          ← settings.json persisted here
```

All four folders are created automatically on first run. Subfolders are preserved — a file at `comics_in/Marvel/issue01.cbz` will land at `comics_out/Marvel/issue01.kepub`.

---

## docker-compose.yml

Adjust the volume paths if your media lives somewhere other than the repo directory.

```yaml
services:
  ereader-converter:
    build: .
    container_name: ereader-converter
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
```

---

## Permissions (PUID / PGID)

The container starts as root, creates an internal user `abc` with the UID/GID you supply, `chown`s the mapped volumes to that user, then immediately drops privileges via `gosu`. Your files on the host remain owned by your normal user.

Run `id` on the host to find your values.

---

## KCC Settings

| Setting | Default | Notes |
|---------|---------|-------|
| Device Profile | `KoLC` (Kobo Libra Colour) | Match your exact device for correct resolution |
| Output Format | `EPUB` | Kobo uses EPUB; Kindle prefers MOBI |
| Cropping | `2` (Margins + Page numbers) | Removes white borders and page numbers |
| Splitter | `2` (Right-then-left) | For manga; set to `1` for western comics |
| Manga Style | off | Enables right-to-left page order |
| High Quality | off | Slower conversion, marginally better output |
| Black Borders | on | Fills unused screen area with black |
| Force Color | on | Preserves color data even on e-ink devices |
| Auto-Contrast | on | Boosts color image contrast automatically |
| Use Filename as Title | on | Sets EPUB metadata title from the source filename |

---

## Behaviour

- The scanner checks `/Books_in` and `/Comics_in` every **10 seconds**.
- Each file gets a per-file lock so the same file is never processed twice concurrently.
- On success: converted file is moved to the output folder, source file is deleted.
- On failure: source file is renamed to `<filename>.failed` so it is not retried in a loop.
- Live logs are shown in the WebUI and streamed to `docker logs`.

---

## Updating

```bash
cd ~/stacks/gittest/ereader-converter && git pull && docker compose up -d --build
```
