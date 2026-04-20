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
BOOKS_IN   = '/Books_in'
BOOKS_OUT  = '/Books_out'

BOOK_EXTS  = {'.epub'}
COMIC_EXTS = {'.cbz', '.cbr', '.zip', '.rar'}

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
    """
    try:
        with open(JOBS_FILE) as f:
            data = json.load(f)
        if isinstance(data, dict):
            with job_registry_lock:
                JOB_REGISTRY.update(data)
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
    failed_path = original + '.failed'
    if not os.path.exists(failed_path):
        return False
    try:
        os.rename(failed_path, original)
    except OSError:
        return False
    _update_job(job_id, state='queued', error=None, started=None, finished=None)
    c_type = job['type']
    with lock_mutex:
        if original not in PROCESSING_LOCKS:
            PROCESSING_LOCKS.add(original)
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


def move_output_file(produced_file: str, target_dir: str) -> None:
    """Move a single conversion output to target_dir, applying any needed renaming."""
    filename = os.path.basename(produced_file)
    if filename.endswith('.kepub.epub'):
        filename = filename[:-len('.kepub.epub')] + '.kepub'
    os.makedirs(target_dir, exist_ok=True)
    candidate = os.path.join(target_dir, filename)
    if os.path.exists(candidate):
        base, ext = os.path.splitext(filename)
        counter = 2
        while os.path.exists(candidate):
            candidate = os.path.join(target_dir, f"{base}_{counter}{ext}")
            counter += 1
    shutil.move(produced_file, candidate)


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
    cmd = [
        'kcc-c2e',
        '--profile',         config['kcc_profile'],
        '--format',          config['kcc_format'],
        '--splitter',        config['kcc_splitter'],
        '--cropping',        config['kcc_cropping'],
        '--croppingpower',   config['kcc_croppingpower'],
        '--croppingminimum', config['kcc_croppingminimum'],
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
    if config['kcc_stretch']:           cmd.append('--stretch')
    if config['kcc_upscale']:           cmd.append('--upscale')
    if config['kcc_nosplitrotate']:     cmd.append('--nosplitrotate')
    if config['kcc_rotate']:            cmd.append('--rotate')
    if config['kcc_nokepub']:           cmd.append('--nokepub')

    if config['kcc_metadatatitle']:
        title = os.path.splitext(os.path.basename(filepath))[0]
        cmd.extend(['--title', title])

    if config.get('kcc_author', '').strip():
        cmd.extend(['--author', config['kcc_author'].strip()])

    if config['kcc_profile'] == 'OTHER':
        if config.get('kcc_customwidth', '').strip():
            cmd.extend(['--customwidth', config['kcc_customwidth'].strip()])
        if config.get('kcc_customheight', '').strip():
            cmd.extend(['--customheight', config['kcc_customheight'].strip()])

    cmd.append(filepath)
    return cmd


def process_file(filepath: str, c_type: str, job_id: str | None = None) -> None:
    """Convert a single file, tracking state in the job registry."""
    short    = os.path.basename(filepath)[:40]
    in_base  = BOOKS_IN if c_type == 'book' else COMICS_IN
    temp_out = os.path.join('/tmp', uuid.uuid4().hex + '_out')

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
                    shutil.move(filepath, _dest)
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
            if os.path.exists(filepath):
                os.rename(filepath, filepath + '.failed')
            _update_job(job_id, state='failed', finished=_now(), error='no output produced')
            _notify('failure', os.path.basename(filepath), 'no output produced')

    except ConversionError as e:
        msg = f'exit {e.returncode}'
        log(f">>> FAILED ({msg}): {short}")
        if os.path.exists(filepath):
            os.rename(filepath, filepath + '.failed')
        _update_job(job_id, state='failed', finished=_now(), error=msg)
        _notify('failure', os.path.basename(filepath), msg)
    except Exception as e:
        msg = str(e)
        log(f">>> ERROR: {short} — {msg}")
        if os.path.exists(filepath):
            os.rename(filepath, filepath + '.failed')
        _update_job(job_id, state='failed', finished=_now(), error=msg)
        _notify('failure', os.path.basename(filepath), msg)
    finally:
        shutil.rmtree(temp_out, ignore_errors=True)
        with lock_mutex:
            PROCESSING_LOCKS.discard(filepath)


def scan_directories() -> None:
    for root, _, files in os.walk(BOOKS_IN):
        for f in files:
            if os.path.splitext(f)[1].lower() in BOOK_EXTS and not f.endswith('.failed'):
                path = os.path.join(root, f)
                with lock_mutex:
                    if path not in PROCESSING_LOCKS:
                        PROCESSING_LOCKS.add(path)
                        threading.Thread(target=process_file,
                                         args=(path, 'book'), daemon=True).start()

    for root, dirs, files in os.walk(COMICS_IN):
        dirs[:] = [d for d in dirs if not (root == COMICS_IN and d == '.archive')]
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

    NOTE: inotify only fires for local filesystems. NFS, SMB/CIFS, and most
    SFTP mounts will not generate events — use poll mode for those setups.
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
            if path.endswith('.failed'):
                return
            if self.c_type == 'comic' and path.startswith(COMICS_ARCHIVE + os.sep):
                return
            with lock_mutex:
                if path not in PROCESSING_LOCKS:
                    PROCESSING_LOCKS.add(path)
                    threading.Thread(
                        target=process_file,
                        args=(path, self.c_type),
                        daemon=True,
                    ).start()

        def on_created(self, event) -> None:  # type: ignore[override]
            # on_created fires as soon as the file appears, before data is
            # written. Still handle it so wait_for_file_ready can do its
            # stability check, but on_closed is the more reliable signal.
            if not event.is_directory:
                self._maybe_dispatch(event.src_path)

        def on_closed(self, event) -> None:  # type: ignore[override]
            # Fires on IN_CLOSE_WRITE — the write handle was closed, meaning
            # the transfer is complete. This is the definitive signal for
            # direct-write clients like FileBrowser. PROCESSING_LOCKS prevents
            # double-dispatch if on_created already queued a thread.
            if not event.is_directory:
                self._maybe_dispatch(event.src_path)

        def on_moved(self, event) -> None:  # type: ignore[override]
            if not event.is_directory:
                self._maybe_dispatch(event.dest_path)

    scan_directories()
    observer = Observer()
    observer.schedule(_Handler('book'),  BOOKS_IN,  recursive=True)
    observer.schedule(_Handler('comic'), COMICS_IN, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except Exception:
        pass
    finally:
        observer.stop()
        observer.join()
