"""File watching, conversion dispatch, and output handling for books and comics."""

import os
import sys
import time
import uuid
import shutil
import threading
import subprocess
from collections import deque

from config import load_config, ConfigDict

COMICS_IN  = '/Comics_in'
COMICS_OUT = '/Comics_out'
BOOKS_IN   = '/Books_in'
BOOKS_OUT  = '/Books_out'

BOOK_EXTS  = {'.epub'}
COMIC_EXTS = {'.cbz', '.cbr', '.zip', '.rar'}

PROCESSING_LOCKS = set()
lock_mutex       = threading.Lock()
LOG_BUFFER       = deque(maxlen=300)
log_lock         = threading.Lock()

# KCC cannot safely run multiple instances concurrently.
# This semaphore ensures only one comic conversion runs at a time.
# Books (kepubify) are unaffected and run in parallel.
kcc_semaphore = threading.Semaphore(1)


def log(msg: str) -> None:
    line = msg.rstrip()
    with log_lock:
        LOG_BUFFER.append(line)
    sys.stdout.write(line + '\n')
    sys.stdout.flush()


def wait_for_file_ready(filepath: str) -> bool:
    """Poll until the file size stabilises, indicating the transfer is complete.

    Polls every 2s for up to 60s (30 attempts). Returns False on timeout; the
    caller logs SKIP and leaves the source untouched so it retries next scan.
    Only definitive failures rename to .failed.
    """
    last_size = -1
    for _ in range(30):
        try:
            if not os.path.exists(filepath):
                return False
            size = os.path.getsize(filepath)
            if size > 0 and size == last_size:
                return True
            last_size = size
        except OSError:
            pass
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
    if config['kcc_blackborders']:      cmd.append('--blackborders')
    if config['kcc_whiteborders']:      cmd.append('--whiteborders')
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


def process_file(filepath: str, c_type: str) -> None:
    short    = os.path.basename(filepath)[:40]
    in_base  = BOOKS_IN if c_type == 'book' else COMICS_IN
    temp_out = os.path.join('/tmp', uuid.uuid4().hex + '_out')
    try:
        if not wait_for_file_ready(filepath):
            log(f">>> SKIP (not ready): {short}")
            return

        config  = load_config()
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
            log(f">>> STARTING: KCC on {short}")
            cmd = _build_kcc_cmd(config, filepath, temp_out)
            log(f">>> QUEUED (waiting for KCC slot): {short}")
            with kcc_semaphore:
                log(f">>> CMD: {' '.join(cmd)}")
                _run_conversion(cmd, short)

        produced = get_output_files(temp_out)
        if produced:
            for f in produced:
                move_output_file(f, target_dir)
            if os.path.exists(filepath):
                os.remove(filepath)
                prune_empty_dirs(filepath, in_base)
            count = len(produced)
            suffix = 's' if count > 1 else ''
            log(f">>> SUCCESS ({count} file{suffix}): {short}")
        else:
            log(f">>> FAILED (no output file found): {short}")
            if os.path.exists(filepath):
                os.rename(filepath, filepath + '.failed')

    except ConversionError as e:
        log(f">>> FAILED (exit {e.returncode}): {short}")
        if os.path.exists(filepath):
            os.rename(filepath, filepath + '.failed')
    except Exception as e:
        log(f">>> ERROR: {short} — {e}")
        if os.path.exists(filepath):
            os.rename(filepath, filepath + '.failed')
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

    for root, _, files in os.walk(COMICS_IN):
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
