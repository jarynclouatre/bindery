import os
import time

old_func = '''def wait_for_file_ready(filepath: str, timeout: int = 60) -> bool:
    """Poll until the file size stabilises, indicating the transfer is complete.

    Polls every 2s for up to 60s (30 attempts). Returns False on timeout; the
    caller logs SKIP and leaves the source untouched so it retries next scan.
    Only definitive failures rename to .failed.
    """
    last_size = -1
    for _ in range(max(1, (timeout + 1) // 2)):
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
    return False'''

new_func = '''def wait_for_file_ready(filepath: str, timeout: int = 60) -> bool:
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
    return False'''

old_handlers = '''        def on_created(self, event) -> None:  # type: ignore[override]
            if not event.is_directory:
                self._maybe_dispatch(event.src_path)

        def on_moved(self, event) -> None:  # type: ignore[override]
            if not event.is_directory:
                self._maybe_dispatch(event.dest_path)'''

new_handlers = '''        def on_created(self, event) -> None:  # type: ignore[override]
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
                self._maybe_dispatch(event.dest_path)'''

if not os.path.exists('processor.py'):
    print("ERROR: processor.py not found in current directory.")
    exit(1)

with open('processor.py', 'r') as f:
    content = f.read()

assert old_func in content, "ERROR: wait_for_file_ready not found - wrong version?"
assert old_handlers in content, "ERROR: inotify handlers not found - wrong version?"

content = content.replace(old_func, new_func)
content = content.replace(old_handlers, new_handlers)

with open('processor.py', 'w') as f:
    f.write(content)

print("OK: processor.py patched")
