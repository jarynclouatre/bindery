"""Raw image folder pipeline — detect, validate, zip, and hand off to Comics_in."""

import os
import time
import uuid
import shutil
import zipfile
import threading

from processor import log

COMICS_RAW             = '/Comics_raw'
COMICS_RAW_PROCESSED   = '/Comics_raw/processed'
COMICS_RAW_UNPROCESSED = '/Comics_raw/unprocessed'
COMICS_IN              = '/Comics_in'

IMAGE_EXTS      = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
IGNORABLE_FILES = {'.ds_store', 'thumbs.db', 'desktop.ini', '.localized'}
STABILITY_SECONDS = 30

RAW_PROCESSING_LOCKS = set()
raw_lock_mutex       = threading.Lock()


def is_folder_stable(folderpath: str) -> bool:
    """Return True if folderpath exists, is non-empty, and no file has been
    modified within the last STABILITY_SECONDS seconds."""
    try:
        entries = os.listdir(folderpath)
    except OSError:
        return False
    newest_mtime = 0.0
    found_any    = False
    for entry in entries:
        full = os.path.join(folderpath, entry)
        try:
            mtime = os.path.getmtime(full)
            found_any = True
            if mtime > newest_mtime:
                newest_mtime = mtime
        except OSError:
            pass
    if not found_any:
        return False
    return (time.time() - newest_mtime) >= STABILITY_SECONDS


def _available_cbz_path(folder_name: str) -> str:
    candidate = os.path.join(COMICS_IN, folder_name + '.cbz')
    if not os.path.exists(candidate):
        return candidate
    counter = 2
    while True:
        candidate = os.path.join(COMICS_IN, f"{folder_name}_{counter}.cbz")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _available_dest_path(parent_dir: str, name: str) -> str:
    candidate = os.path.join(parent_dir, name)
    if not os.path.exists(candidate):
        return candidate
    counter = 2
    while True:
        candidate = os.path.join(parent_dir, f"{name}_{counter}")
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def process_raw_folder(folderpath: str) -> None:
    """Validate, zip, and dispatch a flat image folder into the Comics_in pipeline.

    Rejects folders that contain subfolders or no image files, moving them to
    Comics_raw/unprocessed/ with a log message explaining why. On success the
    original folder is moved to Comics_raw/processed/.
    """
    short    = os.path.basename(folderpath)[:40]
    temp_cbz = os.path.join(os.environ.get("TMPDIR", "/tmp"), uuid.uuid4().hex + ".cbz")
    try:
        try:
            entries = os.listdir(folderpath)
        except OSError as e:
            log(f">>> RAW ERROR: {short} — cannot read folder: {e}")
            return
        subfolders = [e for e in entries if os.path.isdir(os.path.join(folderpath, e))]
        if subfolders:
            log(f">>> RAW SKIPPED: {short} — contains subfolders ({', '.join(subfolders)}). Flatten all images into a single folder with no subdirectories, then drop it into Comics_raw again.")
            os.makedirs(COMICS_RAW_UNPROCESSED, exist_ok=True)
            dest = _available_dest_path(COMICS_RAW_UNPROCESSED, os.path.basename(folderpath))
            shutil.move(folderpath, dest)
            return
        image_files = []
        for entry in entries:
            filepath = os.path.join(folderpath, entry)
            if not os.path.isfile(filepath):
                continue
            ext = os.path.splitext(entry)[1].lower()
            if ext in IMAGE_EXTS:
                image_files.append(filepath)
            elif entry.lower() in IGNORABLE_FILES:
                pass
            else:
                log(f">>> RAW WARNING: {short} — skipping non-image file: {entry}")
        if not image_files:
            log(f">>> RAW SKIPPED: {short} — no image files found. Fix the folder contents and drop it into Comics_raw again.")
            os.makedirs(COMICS_RAW_UNPROCESSED, exist_ok=True)
            dest = _available_dest_path(COMICS_RAW_UNPROCESSED, os.path.basename(folderpath))
            shutil.move(folderpath, dest)
            return
        folder_name = os.path.basename(folderpath)
        log(f">>> RAW ZIPPING: {short} ({len(image_files)} images)")
        with zipfile.ZipFile(temp_cbz, 'w', zipfile.ZIP_STORED) as zf:
            for img in sorted(image_files, key=lambda x: os.path.basename(x).lower()):
                zf.write(img, os.path.basename(img))
        os.makedirs(COMICS_IN, exist_ok=True)
        cbz_path = _available_cbz_path(folder_name)
        shutil.move(temp_cbz, cbz_path)
        os.makedirs(COMICS_RAW_PROCESSED, exist_ok=True)
        processed_dest = _available_dest_path(COMICS_RAW_PROCESSED, folder_name)
        shutil.move(folderpath, processed_dest)
        log(f">>> RAW SUCCESS: {short} -> {os.path.basename(cbz_path)}")
    except Exception as e:
        log(f">>> RAW ERROR: {short} — {e}")
        if os.path.exists(temp_cbz):
            try:
                os.remove(temp_cbz)
            except OSError:
                pass
        if os.path.exists(folderpath):
            try:
                os.makedirs(COMICS_RAW_UNPROCESSED, exist_ok=True)
                dest = _available_dest_path(COMICS_RAW_UNPROCESSED, os.path.basename(folderpath))
                shutil.move(folderpath, dest)
            except OSError:
                pass
    finally:
        with raw_lock_mutex:
            RAW_PROCESSING_LOCKS.discard(folderpath)


def scan_raw_directories() -> None:
    try:
        entries = os.listdir(COMICS_RAW)
    except OSError:
        return
    for entry in entries:
        if entry in ('processed', 'unprocessed'):
            continue
        full_path = os.path.join(COMICS_RAW, entry)
        if not os.path.isdir(full_path):
            continue
        if not is_folder_stable(full_path):
            continue
        with raw_lock_mutex:
            if full_path not in RAW_PROCESSING_LOCKS:
                RAW_PROCESSING_LOCKS.add(full_path)
                threading.Thread(target=process_raw_folder, args=(full_path,), daemon=True).start()


def raw_watch_loop() -> None:
    while True:
        try:
            scan_raw_directories()
        except Exception as e:
            log(f">>> RAW SCAN ERROR: {e}")
        time.sleep(10)


def raw_inotify_watch_loop() -> None:
    """Inotify-based watcher for Comics_raw.

    Triggers scan_raw_directories() immediately when anything appears in
    Comics_raw. The 30-second stability check inside is_folder_stable still
    runs on every trigger, so partially-transferred folders are never processed
    early — inotify just removes the 10-second polling delay.
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class _RawHandler(FileSystemEventHandler):
        def _trigger(self) -> None:
            try:
                scan_raw_directories()
            except Exception as e:
                log(f">>> RAW SCAN ERROR: {e}")

        def on_created(self, event) -> None:  # type: ignore[override]
            self._trigger()

        def on_moved(self, event) -> None:  # type: ignore[override]
            self._trigger()

    scan_raw_directories()
    observer = Observer()
    observer.schedule(_RawHandler(), COMICS_RAW, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except Exception:
        pass
    finally:
        observer.stop()
        observer.join()
