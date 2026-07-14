"""File watching, conversion dispatch, and output handling for books and comics."""

import os
import sys
import time
import uuid
import json
import shutil
import threading
import subprocess
from collections import deque
from datetime import datetime, timezone

from config import DEFAULT_CONFIG, load_config, ConfigDict

COMICS_IN      = '/Comics_in'
COMICS_OUT     = '/Comics_out'
COMICS_ARCHIVE = os.path.join(COMICS_IN, '.archive')
BOOKS_IN       = '/Books_in'
BOOKS_OUT      = '/Books_out'

BOOK_EXTS  = {'.epub'}
COMIC_EXTS = {'.cbz', '.cbr', '.zip', '.rar', '.pdf'}

# Minimum seconds since the last file modification inside a folder before
# treating it as ready for KCC. Prevents processing mid-upload.
FOLDER_STABILITY_SECS = 30

# In inotify mode, a full scan still runs at this interval. Events alone can't
# finish the job: a folder dropped into Comics_in fires its events while still
# unstable, and network mounts fire no events at all.
BACKSTOP_SCAN_SECS = 60

PROCESSING_LOCKS = set()
lock_mutex        = threading.Lock()
LOG_BUFFER        = deque(maxlen=300)
log_lock          = threading.Lock()

# KCC cannot safely run multiple instances concurrently.
# This semaphore ensures only one comic conversion runs at a time.
# Books (kepubify) are unaffected and run in parallel.
kcc_semaphore = threading.Semaphore(1)

LOG_FILE  = '/app/config/bindery.log'
JOBS_FILE = '/app/config/jobs.json'

JOB_REGISTRY: dict[str, dict] = {}
job_registry_lock = threading.Lock()
MAX_JOBS = 500


def log(msg: str) -> None:
    line = msg.rstrip()
    with log_lock:
        LOG_BUFFER.append(line)
        try:
            with open(LOG_FILE, 'a') as f:
                f.write(line + '\n')
        except OSError:
            pass
    sys.stdout.write(line + '\n')
    sys.stdout.flush()


def _load_log_history() -> None:
    """Pre-populate LOG_BUFFER from the persistent log file on startup.
    Trims the file to the last 5000 lines to prevent unbounded growth."""
    try:
        with open(LOG_FILE) as f:
            lines = f.read().splitlines()
        if len(lines) > 5000:
            lines = lines[-5000:]
            try:
                with open(LOG_FILE, 'w') as f:
                    f.write('\n'.join(lines) + '\n')
            except OSError:
                pass
        with log_lock:
            for line in lines[-300:]:
                LOG_BUFFER.append(line)
    except OSError:
        pass


def _load_job_registry() -> None:
    """Load persisted job registry from disk on startup.

    Uses .update() on the existing dict so that references imported by other
    modules (e.g. app.py) continue to point at the same object.

    Jobs persisted as queued/processing belonged to threads that died with the
    previous process — their sources are still in the watch folders and get
    picked up as fresh jobs, so the stale entries are dropped rather than left
    as permanent "processing" rows in the UI.
    """
    try:
        with open(JOBS_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            with job_registry_lock:
                JOB_REGISTRY.update(
                    (k, v) for k, v in data.items()
                    if isinstance(v, dict) and v.get('state') in ('success', 'failed')
                )
                _save_job_registry()
    except (OSError, json.JSONDecodeError):
        pass


def _save_job_registry() -> None:
    """Atomically write job registry to disk. Caller must hold job_registry_lock."""
    try:
        os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
        tmp = JOBS_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(JOB_REGISTRY, f)
        os.replace(tmp, JOBS_FILE)
    except OSError:
        pass


def _now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _register_job(filepath: str, c_type: str) -> str:
    """Create a new QUEUED job entry and return its ID."""
    job_id = uuid.uuid4().hex
    entry: dict = {
        'id':       job_id,
        'filename': os.path.basename(filepath),
        'filepath': filepath,
        'type':     c_type,
        'state':    'queued',
        'created':  _now(),
        'started':  None,
        'finished': None,
        'error':    None,
    }
    with job_registry_lock:
        JOB_REGISTRY[job_id] = entry
        if len(JOB_REGISTRY) > MAX_JOBS:
            # Prune oldest completed jobs first, then by created time
            candidates = sorted(
                JOB_REGISTRY,
                key=lambda k: (
                    0 if JOB_REGISTRY[k]['state'] in ('success', 'failed') else 1,
                    JOB_REGISTRY[k].get('created') or '',
                )
            )
            for k in candidates[:len(JOB_REGISTRY) - MAX_JOBS]:
                del JOB_REGISTRY[k]
        _save_job_registry()
    return job_id


def _update_job(job_id: str | None, **kwargs: object) -> None:
    """Update fields on a job entry and persist. No-op if job_id is None or unknown."""
    if job_id is None:
        return
    with job_registry_lock:
        if job_id in JOB_REGISTRY:
            JOB_REGISTRY[job_id].update(kwargs)
            _save_job_registry()


def _notify(event: str, filename: str, error: str | None = None) -> None:
    """Send an Apprise notification if configured for this event type."""
    try:
        config = load_config()
        urls   = config.get('apprise_urls', '').strip()
        if not urls:
            return
        if event == 'success' and not config.get('notify_on_success', DEFAULT_CONFIG['notify_on_success']):
            return
        if event == 'failure' and not config.get('notify_on_failure', DEFAULT_CONFIG['notify_on_failure']):
            return
        import apprise
        ap = apprise.Apprise()
        for url in urls.splitlines():
            url = url.strip()
            if url:
                ap.add(url)
        if event == 'success':
            title = 'Bindery: Conversion complete'
            body  = f'\u2713 {filename}'
        else:
            title = 'Bindery: Conversion failed'
            body  = f'\u2717 {filename}' + (f'\n{error}' if error else '')
        ap.notify(title=title, body=body)
    except Exception as e:
        log(f'>>> NOTIFY ERROR: {e}')


def retry_file(job_id: str) -> bool:
    """Rename the .failed file back to its original name and re-dispatch it.

    Returns True if the retry was successfully queued.
    """
    with job_registry_lock:
        job = JOB_REGISTRY.get(job_id)
    if not job or job['state'] != 'failed':
        return False
    original    = job['filepath']
    failed_path = job.get('failed_path') or (original + '.failed')
    if not os.path.exists(failed_path):
        return False
    if os.path.exists(original):
        # Something new was dropped under the original name — don't clobber it.
        return False
    try:
        os.rename(failed_path, original)
    except OSError:
        return False
    _update_job(job_id, state='queued', error=None, started=None, finished=None, failed_path=None)
    c_type = job['type']
    with lock_mutex:
        if original not in PROCESSING_LOCKS:
            PROCESSING_LOCKS.add(original)
            if os.path.isdir(original):
                threading.Thread(target=process_folder, args=(original, job_id), daemon=True).start()
            else:
                threading.Thread(target=process_file, args=(original, c_type, job_id), daemon=True).start()
    return True


def wait_for_file_ready(filepath: str, timeout: int = 60) -> bool:
    """Poll until the file size stabilises, indicating the transfer is complete.

    Polls every 2s for up to `timeout` seconds. Requires STABLE_NEEDED
    consecutive identical non-zero size readings before declaring the file
    ready. A single 2-second stable window is not enough — copy tools like
    FileBrowser pause briefly between write chunks, which fools a one-shot
    stability check into processing a still-incomplete file.

    Returns False on timeout; the caller logs SKIP and leaves the source
    untouched so it retries next scan. Only definitive failures rename to
    .failed.
    """
    STABLE_NEEDED = 3  # require ~6 s of stable size before processing
    last_size    = -1
    stable_count =  0
    for _ in range(max(1, (timeout + 1) // 2)):
        try:
            if not os.path.exists(filepath):
                return False
            size = os.path.getsize(filepath)
            if size > 0 and size == last_size:
                stable_count += 1
                if stable_count >= STABLE_NEEDED:
                    return True
            else:
                stable_count = 0
                last_size = size
        except OSError:
            stable_count = 0
        time.sleep(2)
    return False


def _is_dir_stable(dirpath: str) -> bool:
    """Return True if dirpath is non-empty and no file inside was modified recently.

    Walks the directory recursively and checks that the newest mtime is at least
    FOLDER_STABILITY_SECS seconds in the past. An empty directory returns False —
    it may still be populated.
    """
    newest    = 0.0
    found_any = False
    for root, _dirs, files in os.walk(dirpath):
        for fname in files:
            try:
                mtime = os.path.getmtime(os.path.join(root, fname))
                found_any = True
                if mtime > newest:
                    newest = mtime
            except OSError:
                pass
    if not found_any:
        return False
    return (time.time() - newest) >= FOLDER_STABILITY_SECS


def get_output_files(directory: str) -> list[str]:
    """Return all files in directory, sorted oldest to newest."""
    files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
    ]
    return sorted(files, key=os.path.getmtime)


def prune_empty_dirs(file_path: str, stop_at: str) -> None:
    """Walk upward from file_path's directory, removing empty dirs until stop_at."""
    d = os.path.dirname(os.path.abspath(file_path))
    stop_at = os.path.abspath(stop_at)
    while d != stop_at and d.startswith(stop_at + os.sep):
        try:
            os.rmdir(d)
            d = os.path.dirname(d)
        except OSError:
            break


def _collision_free(dest: str) -> str:
    """Return dest, or dest with a _2/_3/... suffix if something already lives there."""
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    counter = 2
    while True:
        candidate = f"{base}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def _rename_failed(path: str) -> str | None:
    """Rename a failed source to <path>.failed without clobbering earlier failures.

    Collisions become <path>_2.failed etc. so the name always ends in .failed
    and stays invisible to the scanners. Returns the new path, or None if the
    rename itself failed (source vanished, permissions).
    """
    candidate = path + '.failed'
    counter = 2
    while os.path.exists(candidate):
        candidate = f"{path}_{counter}.failed"
        counter += 1
    try:
        os.rename(path, candidate)
        return candidate
    except OSError:
        return None


_output_move_lock = threading.Lock()


def move_output_file(produced_file: str, target_dir: str) -> None:
    """Move a single conversion output to target_dir, applying any needed renaming."""
    filename = os.path.basename(produced_file)
    if filename.endswith('.kepub.epub'):
        filename = filename[:-len('.kepub.epub')] + '.kepub'
    os.makedirs(target_dir, exist_ok=True)
    # Books convert in parallel; the lock keeps two same-named outputs from
    # both picking the same collision-free name and overwriting each other.
    with _output_move_lock:
        shutil.move(produced_file, _collision_free(os.path.join(target_dir, filename)))


class ConversionError(Exception):
    """Raised when a converter process exits with a non-zero return code."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def _run_conversion(cmd: list[str], short: str) -> None:
    """Run cmd, streaming output to the log. Raises ConversionError on non-zero exit."""
    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    for line in process.stdout:
        log(f"[{short}] {line.rstrip()}")
    process.wait()
    if process.returncode != 0:
        raise ConversionError(process.returncode)


def _build_kcc_cmd(config: ConfigDict, filepath: str, temp_out: str) -> list[str]:
    """Build and return the kcc-c2e argument list from the current config."""
    # MOBI needs kindlegen and KFX needs a Calibre plugin — neither exists in
    # this container, so configs that predate their removal fall back to EPUB.
    fmt = config['kcc_format'] if config['kcc_format'] in ('EPUB', 'CBZ') else 'EPUB'

    # The UI takes cropping minimum as a percentage; kcc-c2e wants a 0-1 ratio.
    try:
        crop_min = float(config['kcc_croppingminimum']) / 100
    except (TypeError, ValueError):
        crop_min = 0.0

    cmd = [
        'kcc-c2e',
        '--profile',         config['kcc_profile'],
        '--format',          fmt,
        '--splitter',        config['kcc_splitter'],
        '--cropping',        config['kcc_cropping'],
        '--croppingpower',   config['kcc_croppingpower'],
        '--croppingminimum', str(crop_min),
        '--batchsplit',      config['kcc_batchsplit'],
        '--output',          temp_out,
    ]

    gamma = config.get('kcc_gamma', '0')
    if gamma and gamma != '0':
        cmd.extend(['--gamma', gamma])

    if config['kcc_manga_style']:       cmd.append('--manga-style')
    if config['kcc_hq']:                cmd.append('--hq')
    if config['kcc_two_panel']:         cmd.append('--two-panel')
    if config['kcc_webtoon']:           cmd.append('--webtoon')
    if config.get('kcc_borders') == 'black': cmd.append('--blackborders')
    if config.get('kcc_borders') == 'white': cmd.append('--whiteborders')
    if config['kcc_forcecolor']:        cmd.append('--forcecolor')
    if config['kcc_colorautocontrast']: cmd.append('--colorautocontrast')
    if config['kcc_colorcurve']:        cmd.append('--colorcurve')
    if config.get('kcc_eraserainbow'): cmd.append('--eraserainbow')
    if config.get('kcc_mozjpeg'):       cmd.append('--mozjpeg')
    if config['kcc_stretch']:           cmd.append('--stretch')
    if config['kcc_upscale']:           cmd.append('--upscale')
    if config['kcc_nosplitrotate']:     cmd.append('--nosplitrotate')
    if config['kcc_rotate']:            cmd.append('--rotate')
    if config['kcc_nokepub']:           cmd.append('--nokepub')

    # = form, so filenames/authors starting with a dash don't read as options
    if config['kcc_metadatatitle']:
        title = os.path.splitext(os.path.basename(filepath))[0]
        cmd.append('--title=' + title)

    if config.get('kcc_author', '').strip():
        cmd.append('--author=' + config['kcc_author'].strip())

    if config['kcc_profile'] == 'OTHER':
        if config.get('kcc_customwidth', '').strip():
            cmd.extend(['--customwidth', config['kcc_customwidth'].strip()])
        if config.get('kcc_customheight', '').strip():
            cmd.extend(['--customheight', config['kcc_customheight'].strip()])

    cmd.append(filepath)
    return cmd


def _strip_leading_dash(filepath: str, job_id: str) -> str:
    """Rename a dash-leading source file so KCC's 7z call doesn't eat it.

    KCC extracts archives by running 7z with the bare basename (cwd-relative),
    and 7z parses a leading dash as a switch — every such file would fail. The
    rename is logged and the job's filepath updated so Retry follows it.
    """
    base = os.path.basename(filepath)
    if not base.startswith('-'):
        return filepath
    stripped = base.lstrip('- ')
    if not stripped or stripped.startswith('.'):
        stripped = 'file' + os.path.splitext(base)[1]
    safe = _collision_free(os.path.join(os.path.dirname(filepath), stripped))
    try:
        os.rename(filepath, safe)
    except OSError:
        return filepath
    log(f">>> RENAMED (leading dash breaks extraction): {base} -> {os.path.basename(safe)}")
    _update_job(job_id, filepath=safe, filename=os.path.basename(safe))
    return safe


def process_file(filepath: str, c_type: str, job_id: str | None = None) -> None:
    """Convert a single file, tracking state in the job registry."""
    short    = os.path.basename(filepath)[:40]
    in_base  = BOOKS_IN if c_type == 'book' else COMICS_IN
    temp_out = os.path.join('/tmp', uuid.uuid4().hex + '_out')
    lock_key = filepath

    try:
        # Register inside try so PROCESSING_LOCKS.discard always runs in finally.
        if job_id is None:
            job_id = _register_job(filepath, c_type)

        config = load_config()
        if not wait_for_file_ready(filepath, int(config.get('file_wait_timeout', 60))):
            log(f">>> SKIP (not ready): {short}")
            # Remove job so the next scan creates a fresh one
            with job_registry_lock:
                JOB_REGISTRY.pop(job_id, None)
                _save_job_registry()
            return

        if c_type == 'comic':
            filepath = _strip_leading_dash(filepath, job_id)
            short    = os.path.basename(filepath)[:40]

        _update_job(job_id, state='processing', started=_now())

        rel_dir = os.path.relpath(os.path.dirname(filepath), in_base)
        if rel_dir == '.':
            rel_dir = ''
        out_base   = BOOKS_OUT if c_type == 'book' else COMICS_OUT
        target_dir = os.path.join(out_base, rel_dir) if rel_dir else out_base
        os.makedirs(temp_out, exist_ok=True)

        if c_type == 'book':
            log(f">>> STARTING: kepubify on {short}")
            cmd = ['kepubify', '--calibre', '--inplace', '--output', temp_out, filepath]
            _run_conversion(cmd, short)

        else:
            cmd = _build_kcc_cmd(config, filepath, temp_out)
            log(f">>> QUEUED: {short}")
            with kcc_semaphore:
                log(f">>> STARTING: kcc-c2e on {short}")
                log(f">>> CMD: {' '.join(cmd)}")
                _run_conversion(cmd, short)

        produced = get_output_files(temp_out)
        if produced:
            for f in produced:
                move_output_file(f, target_dir)
            if os.path.exists(filepath):
                if c_type == 'comic' and config.get('preserve_originals', False):
                    _dest = os.path.join(COMICS_ARCHIVE, os.path.relpath(filepath, COMICS_IN))
                    os.makedirs(os.path.dirname(_dest), exist_ok=True)
                    shutil.move(filepath, _collision_free(_dest))
                else:
                    os.remove(filepath)
                prune_empty_dirs(filepath, in_base)
            count  = len(produced)
            suffix = 's' if count > 1 else ''
            log(f">>> SUCCESS ({count} file{suffix}): {short}")
            _update_job(job_id, state='success', finished=_now())
            _notify('success', os.path.basename(filepath))
        else:
            log(f">>> FAILED (no output file found): {short}")
            failed_path = _rename_failed(filepath) if os.path.exists(filepath) else None
            _update_job(job_id, state='failed', finished=_now(),
                        error='no output produced', failed_path=failed_path)
            _notify('failure', os.path.basename(filepath), 'no output produced')

    except ConversionError as e:
        msg = f'exit {e.returncode}'
        log(f">>> FAILED ({msg}): {short}")
        failed_path = _rename_failed(filepath) if os.path.exists(filepath) else None
        _update_job(job_id, state='failed', finished=_now(), error=msg, failed_path=failed_path)
        _notify('failure', os.path.basename(filepath), msg)
    except Exception as e:
        msg = str(e)
        log(f">>> ERROR: {short} — {msg}")
        failed_path = _rename_failed(filepath) if os.path.exists(filepath) else None
        _update_job(job_id, state='failed', finished=_now(), error=msg, failed_path=failed_path)
        _notify('failure', os.path.basename(filepath), msg)
    finally:
        shutil.rmtree(temp_out, ignore_errors=True)
        with lock_mutex:
            PROCESSING_LOCKS.discard(lock_key)


def process_folder(folderpath: str, job_id: str | None = None) -> None:
    """Convert a folder of comic files as a single bundled KCC volume.

    KCC accepts a directory as its input argument and treats the contents as
    chapters of one volume. The folder is removed (or archived) on success,
    or renamed to <name>.failed on error.
    """
    short    = os.path.basename(folderpath)[:40]
    temp_out = os.path.join('/tmp', uuid.uuid4().hex + '_out')

    try:
        if job_id is None:
            job_id = _register_job(folderpath, 'comic')

        if not _is_dir_stable(folderpath):
            log(f">>> SKIP (not ready): {short}/")
            with job_registry_lock:
                JOB_REGISTRY.pop(job_id, None)
                _save_job_registry()
            return

        _update_job(job_id, state='processing', started=_now())

        config = load_config()
        os.makedirs(temp_out, exist_ok=True)
        cmd    = _build_kcc_cmd(config, folderpath, temp_out)

        log(f">>> QUEUED (folder): {short}/")
        with kcc_semaphore:
            log(f">>> STARTING: kcc-c2e on {short}/")
            log(f">>> CMD: {' '.join(cmd)}")
            _run_conversion(cmd, short)

        produced = get_output_files(temp_out)
        if produced:
            for f in produced:
                move_output_file(f, COMICS_OUT)
            if os.path.exists(folderpath):
                if config.get('preserve_originals', False):
                    _dest = os.path.join(COMICS_ARCHIVE, os.path.basename(folderpath))
                    os.makedirs(COMICS_ARCHIVE, exist_ok=True)
                    shutil.move(folderpath, _collision_free(_dest))
                else:
                    shutil.rmtree(folderpath)
            count  = len(produced)
            suffix = 's' if count > 1 else ''
            log(f">>> SUCCESS ({count} file{suffix}): {short}/")
            _update_job(job_id, state='success', finished=_now())
            _notify('success', short + '/')
        else:
            log(f">>> FAILED (no output file found): {short}/")
            failed_path = _rename_failed(folderpath) if os.path.exists(folderpath) else None
            _update_job(job_id, state='failed', finished=_now(),
                        error='no output produced', failed_path=failed_path)
            _notify('failure', short + '/', 'no output produced')

    except ConversionError as e:
        msg = f'exit {e.returncode}'
        log(f">>> FAILED ({msg}): {short}/")
        failed_path = _rename_failed(folderpath) if os.path.exists(folderpath) else None
        _update_job(job_id, state='failed', finished=_now(), error=msg, failed_path=failed_path)
        _notify('failure', short + '/', msg)
    except Exception as e:
        msg = str(e)
        log(f">>> ERROR: {short}/ — {msg}")
        failed_path = _rename_failed(folderpath) if os.path.exists(folderpath) else None
        _update_job(job_id, state='failed', finished=_now(), error=msg, failed_path=failed_path)
        _notify('failure', short + '/', msg)
    finally:
        shutil.rmtree(temp_out, ignore_errors=True)
        with lock_mutex:
            PROCESSING_LOCKS.discard(folderpath)


def _contains_comic_archives(dirpath: str) -> bool:
    """True if any file under dirpath has a comic archive extension."""
    for _root, _dirs, files in os.walk(dirpath):
        for f in files:
            if os.path.splitext(f)[1].lower() in COMIC_EXTS:
                return True
    return False


def scan_directories() -> None:
    for root, dirs, files in os.walk(BOOKS_IN):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not d.endswith('.failed')]
        for f in files:
            if os.path.splitext(f)[1].lower() in BOOK_EXTS and not f.endswith('.failed'):
                path = os.path.join(root, f)
                with lock_mutex:
                    if path not in PROCESSING_LOCKS:
                        PROCESSING_LOCKS.add(path)
                        threading.Thread(target=process_file,
                                         args=(path, 'book'), daemon=True).start()

    # Dispatch top-level Comics_in image folders as bundled KCC jobs. Folders
    # that contain archives are left to the per-file walk below instead — KCC
    # rejects nested archives ("No images detected") when given such a folder.
    folder_job_names: set[str] = set()
    try:
        top_entries = os.listdir(COMICS_IN)
    except OSError:
        top_entries = []
    for entry in top_entries:
        if entry.startswith('.') or entry.endswith('.failed'):
            continue
        full = os.path.join(COMICS_IN, entry)
        if not os.path.isdir(full) or _contains_comic_archives(full):
            continue
        folder_job_names.add(entry)
        with lock_mutex:
            if full not in PROCESSING_LOCKS:
                PROCESSING_LOCKS.add(full)
                threading.Thread(target=process_folder, args=(full,), daemon=True).start()

    for root, dirs, files in os.walk(COMICS_IN):
        if root == COMICS_IN:
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.endswith('.failed')
                       and d not in folder_job_names]
        else:
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.endswith('.failed')]
        for f in files:
            if os.path.splitext(f)[1].lower() in COMIC_EXTS and not f.endswith('.failed'):
                path = os.path.join(root, f)
                with lock_mutex:
                    if path not in PROCESSING_LOCKS:
                        PROCESSING_LOCKS.add(path)
                        threading.Thread(target=process_file,
                                         args=(path, 'comic'), daemon=True).start()


def watch_loop() -> None:
    while True:
        try:
            scan_directories()
        except Exception as e:
            log(f">>> SCAN ERROR: {e}")
        time.sleep(10)


def inotify_watch_loop() -> None:
    """Inotify-based watcher for Books_in and Comics_in.

    Uses watchdog's Observer (inotify on Linux). Dispatches process_file on
    FileCreatedEvent and FileMovedEvent, so both direct writes and
    temp-file-then-rename patterns (e.g. WinSCP) are handled correctly.
    wait_for_file_ready still runs inside process_file, so partial writes
    from direct-write clients are tolerated.

    inotify does not fire for NFS/SMB mounts, and folder jobs are usually not
    stable yet when their events arrive, so a slow backstop scan runs every
    BACKSTOP_SCAN_SECS to catch anything the events missed.
    """
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class _Handler(FileSystemEventHandler):
        def __init__(self, c_type: str) -> None:
            self.c_type = c_type
            self.exts   = BOOK_EXTS if c_type == 'book' else COMIC_EXTS

        def _maybe_dispatch(self, path: str) -> None:
            if os.path.splitext(path)[1].lower() not in self.exts:
                return
            if any(part.startswith('.') or part.endswith('.failed')
                   for part in path.split(os.sep) if part):
                return
            if self.c_type == 'comic':
                rel = os.path.relpath(os.path.abspath(path), os.path.abspath(COMICS_IN))
                parts = rel.split(os.sep)
                if len(parts) > 1:
                    top = os.path.join(COMICS_IN, parts[0])
                    if not _contains_comic_archives(top):
                        # Pure image folder — it's one bundled volume, never
                        # converted piecemeal. Poke the folder job instead.
                        self._maybe_dispatch_dir(top)
                        return
                    # Folders holding archives convert per-file; fall through.
            with lock_mutex:
                if path not in PROCESSING_LOCKS:
                    PROCESSING_LOCKS.add(path)
                    threading.Thread(
                        target=process_file,
                        args=(path, self.c_type),
                        daemon=True,
                    ).start()

        def _maybe_dispatch_dir(self, path: str) -> None:
            # Only top-level directories directly inside Comics_in are treated
            # as bundled folder jobs. Deeper directories are ignored here.
            if os.path.dirname(os.path.abspath(path)) != os.path.abspath(COMICS_IN):
                return
            base = os.path.basename(path)
            if base.startswith('.') or base.endswith('.failed'):
                return
            if _contains_comic_archives(path):
                # Archives inside convert per-file — KCC can't bundle them.
                return
            with lock_mutex:
                if path not in PROCESSING_LOCKS:
                    PROCESSING_LOCKS.add(path)
                    threading.Thread(target=process_folder, args=(path,), daemon=True).start()

        def on_created(self, event) -> None:  # type: ignore[override]
            # on_created fires as soon as the file appears, before data is
            # written. Still handle it so wait_for_file_ready can do its
            # stability check, but on_closed is the more reliable signal.
            if event.is_directory:
                if self.c_type == 'comic':
                    self._maybe_dispatch_dir(event.src_path)
            else:
                self._maybe_dispatch(event.src_path)

        def on_closed(self, event) -> None:  # type: ignore[override]
            # Fires on IN_CLOSE_WRITE — the write handle was closed, meaning
            # the transfer is complete. This is the definitive signal for
            # direct-write clients like FileBrowser. PROCESSING_LOCKS prevents
            # double-dispatch if on_created already queued a thread.
            if not event.is_directory:
                self._maybe_dispatch(event.src_path)

        def on_moved(self, event) -> None:  # type: ignore[override]
            if event.is_directory:
                if self.c_type == 'comic':
                    self._maybe_dispatch_dir(event.dest_path)
            else:
                self._maybe_dispatch(event.dest_path)

    scan_directories()
    observer = Observer()
    observer.schedule(_Handler('book'),  BOOKS_IN,  recursive=True)
    observer.schedule(_Handler('comic'), COMICS_IN, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(BACKSTOP_SCAN_SECS)
            try:
                scan_directories()
            except Exception as e:
                log(f">>> SCAN ERROR: {e}")
    finally:
        observer.stop()
        observer.join()
