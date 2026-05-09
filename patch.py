#!/usr/bin/env python3
"""
v3.3.0 — Add PDF support for comics.

Changes:
  - processor.py        : add '.pdf' to COMIC_EXTS
  - app.py              : VERSION 3.2.0 -> 3.3.0
  - pyproject.toml      : version 3.2.0 -> 3.3.0
  - README.md           : list .pdf in intro and folder-layout block
  - CHANGELOG.md        : prepend v3.3.0 entry
  - tests/test_processor.py : add PDF dispatch test
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def patch(path, old, new, *, count=1):
    p = ROOT / path
    text = p.read_text()
    found = text.count(old)
    if found != count:
        sys.exit(f"FAIL {path}: expected {count} match(es), found {found} for:\n{old!r}")
    p.write_text(text.replace(old, new, count))
    print(f"  patched {path}")

# ── processor.py: add .pdf to COMIC_EXTS ─────────────────────────────────────
patch(
    "processor.py",
    "COMIC_EXTS = {'.cbz', '.cbr', '.zip', '.rar'}",
    "COMIC_EXTS = {'.cbz', '.cbr', '.zip', '.rar', '.pdf'}",
)

# ── app.py: bump VERSION ─────────────────────────────────────────────────────
patch("app.py", 'VERSION = "3.2.0"', 'VERSION = "3.3.0"')

# ── pyproject.toml: bump version ─────────────────────────────────────────────
patch("pyproject.toml", 'version = "3.2.0"', 'version = "3.3.0"')

# ── README.md: intro line listing comic formats ──────────────────────────────
patch(
    "README.md",
    "Converts comic archives (`.cbz`, `.cbr`, `.zip`, `.rar`) into device-optimised files",
    "Converts comic archives and PDFs (`.cbz`, `.cbr`, `.zip`, `.rar`, `.pdf`) into device-optimised files",
)

# ── README.md: folder layout comment ─────────────────────────────────────────
patch(
    "README.md",
    "├── comics_in/       ← drop .cbz / .cbr / .zip / .rar here",
    "├── comics_in/       ← drop .cbz / .cbr / .zip / .rar / .pdf here",
)

# ── CHANGELOG.md: prepend new entry ──────────────────────────────────────────
changelog = ROOT / "CHANGELOG.md"
old_top = "## v3.2.0 — Optional chown Skip"
new_entry = (
    "## v3.3.0 — PDF Support for Comics\n"
    "\n"
    "- Added: `.pdf` is now recognised as a comic input format — drop PDFs into `Comics_in` and they'll be picked up by both the poll scan and inotify watcher, then converted with KCC; KCC supports PDF as a first-class input alongside CBZ/CBR\n"
    "- Note: EPUBs continue to be handled by the books pipeline (kepubify); KCC does not accept EPUB as input, so graphic-novel EPUBs should be dropped in `Books_in`\n"
    "\n"
)
text = changelog.read_text()
if not text.startswith(old_top):
    sys.exit(f"FAIL CHANGELOG.md: top entry does not start with {old_top!r}")
changelog.write_text(new_entry + text)
print("  patched CHANGELOG.md")

# ── tests/test_processor.py: add PDF dispatch test ───────────────────────────
testfile = ROOT / "tests" / "test_processor.py"
text = testfile.read_text()

anchor = "def test_scan_directories_skips_failed_files(tmp_path):"
new_test = (
    "def test_scan_directories_dispatches_pdf_comic(tmp_path):\n"
    "    \"\"\"PDFs in Comics_in should be dispatched (KCC accepts PDF as input).\"\"\"\n"
    "    comics_in = tmp_path / 'comics_in'\n"
    "    books_in  = tmp_path / 'books_in'\n"
    "    comics_in.mkdir()\n"
    "    books_in.mkdir()\n"
    "    (comics_in / 'test.pdf').write_bytes(b'x')\n"
    "\n"
    "    dispatched = []\n"
    "    with patch.object(processor, 'COMICS_IN', str(comics_in)), \\\n"
    "         patch.object(processor, 'BOOKS_IN',  str(books_in)), \\\n"
    "         patch('processor.threading') as mock_threading:\n"
    "        def _fake_thread(target, args, daemon): dispatched.append(args); return MagicMock()\n"
    "        mock_threading.Thread = MagicMock(side_effect=_fake_thread)\n"
    "        processor.PROCESSING_LOCKS.clear()\n"
    "        processor.scan_directories()\n"
    "\n"
    "    assert any(str(comics_in / 'test.pdf') in str(a) for a in dispatched)\n"
    "\n"
    "\n"
)
if anchor not in text:
    sys.exit(f"FAIL tests/test_processor.py: anchor not found: {anchor!r}")
testfile.write_text(text.replace(anchor, new_test + anchor, 1))
print("  patched tests/test_processor.py")

print("\nAll patches applied.")
