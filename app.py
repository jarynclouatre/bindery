"""Flask application factory, WebUI routes, and form validation."""

import os
import re
import signal
import time
import uuid
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, request, render_template, send_file

from config import DEFAULT_CONFIG, KCC_KEYS, load_config, save_config, ConfigDict
from processor import (
    LOG_BUFFER, log_lock, log, watch_loop, inotify_watch_loop,
    _load_log_history, _load_job_registry, _collision_free,
    JOB_REGISTRY, job_registry_lock, retry_file,
    BOOK_EXTS, COMIC_EXTS,
    BOOKS_IN, BOOKS_OUT, COMICS_IN, COMICS_OUT,
)
from raw_processor import raw_watch_loop, raw_inotify_watch_loop

VERSION = "4.0.0"


def _clamp(value: object, min_val: float, max_val: float, default: float) -> str:
    """Parse value as float, clamping to [min_val, max_val]. Returns default on invalid input."""
    try:
        return str(max(min_val, min(max_val, float(value))))
    except (ValueError, TypeError):
        return str(default)


def _validate_post(config: ConfigDict) -> ConfigDict:
    """Clamp numeric fields to their valid ranges after reading from the form."""
    config['kcc_croppingpower']   = _clamp(config['kcc_croppingpower'],   0.1, 2.0, 1.0)
    config['kcc_croppingminimum'] = _clamp(config['kcc_croppingminimum'],   0, 100,  0)
    for key in ('kcc_customwidth', 'kcc_customheight'):
        val = config[key].strip()
        if val:
            try:
                config[key] = str(max(0, int(val)))
            except (ValueError, TypeError):
                config[key] = ''

    _VALID_BORDERS    = {'none', 'black', 'white'}
    _VALID_GAMMA      = {'0', '0.5', '0.8', '1.0', '1.2', '1.5', '1.8', '2.0', '2.2'}
    _VALID_PROFILE    = {
        'K1', 'K2', 'K11', 'K34', 'K57', 'K810', 'KDX', 'KPW', 'KPW34', 'KPW5',
        'KV', 'KO', 'KCS', 'KS', 'KS3', 'KSCS', 'KS1860', 'KS1920',
        'KoMT', 'KoG', 'KoGHD', 'KoA', 'KoAHD', 'KoAH2O', 'KoAO',
        'KoN', 'KoF', 'KoS', 'KoC', 'KoCC', 'KoL', 'KoLC', 'KoE',
        'Rmk1', 'Rmk2', 'RmkPP', 'RmkPPMove', 'OTHER',
    }
    # MOBI needs kindlegen and KFX needs a Calibre plugin — neither can ship
    # in this image, so only formats that actually convert are accepted.
    _VALID_FORMAT     = {'EPUB', 'CBZ'}
    _VALID_CROPPING   = {'0', '1', '2'}
    _VALID_SPLITTER   = {'0', '1', '2', '3', '4'}
    _VALID_BATCHSPLIT = {'0', '1', '2'}

    if config['kcc_borders']    not in _VALID_BORDERS:    config['kcc_borders']    = 'black'
    if config['kcc_gamma']      not in _VALID_GAMMA:      config['kcc_gamma']      = '0'
    if config['kcc_profile']    not in _VALID_PROFILE:    config['kcc_profile']    = DEFAULT_CONFIG['kcc_profile']
    if config['kcc_format']     not in _VALID_FORMAT:     config['kcc_format']     = 'EPUB'
    if config['kcc_cropping']   not in _VALID_CROPPING:   config['kcc_cropping']   = '2'
    if config['kcc_splitter']   not in _VALID_SPLITTER:   config['kcc_splitter']   = '1'
    if config['kcc_batchsplit'] not in _VALID_BATCHSPLIT: config['kcc_batchsplit'] = '0'

    try:
        config['file_wait_timeout'] = int(max(10, min(300, int(config.get('file_wait_timeout', 60)))))
    except (ValueError, TypeError):
        config['file_wait_timeout'] = 60

    if config.get('watcher_mode') not in ('poll', 'inotify'):
        config['watcher_mode'] = 'poll'

    config['apprise_urls'] = config.get('apprise_urls', '')

    return config


def create_app(start_threads: bool = True) -> Flask:
    app = Flask(__name__)
    # Werkzeug spools big uploads to disk, so the cap is about sanity, not RAM.
    app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({'error': 'File too large (4 GB max per upload)'}), 413

    @app.route('/api/upload', methods=['POST'])
    def api_upload():
        uploads = request.files.getlist('files')
        if not uploads:
            return jsonify({'error': 'no files'}), 400
        profile  = (request.form.get('profile') or '').strip()
        config   = load_config()
        profiles = config.get('profiles') or {}
        results  = []
        for f in uploads:
            name = os.path.basename(f.filename or '').lstrip('.')
            ext  = os.path.splitext(name)[1].lower()
            if not name or ext not in BOOK_EXTS | COMIC_EXTS:
                results.append({'name': f.filename or '?', 'error': 'unsupported file type'})
                continue
            if ext in BOOK_EXTS:
                base = BOOKS_IN
            else:
                base = os.path.join(COMICS_IN, profile) if profile in profiles else COMICS_IN
            # Land in a hidden dir the watchers ignore, then rename into place
            # so the scanner only ever sees complete files.
            hold = os.path.join(base, '.uploading')
            os.makedirs(hold, exist_ok=True)
            part = os.path.join(hold, uuid.uuid4().hex + '.part')
            try:
                f.save(part)
                dest = _collision_free(os.path.join(base, name))
                os.replace(part, dest)
            except OSError as e:
                try:
                    os.remove(part)
                except OSError:
                    pass
                results.append({'name': name, 'error': str(e)})
                continue
            log(f">>> Uploaded via WebUI: {os.path.relpath(dest, base)} → {base}")
            results.append({'name': os.path.basename(dest), 'ok': True})
        return jsonify({'files': results})

    @app.route('/api/logs')
    def api_logs():
        with log_lock:
            logs = list(LOG_BUFFER)
        return jsonify({'logs': logs})

    @app.route('/api/status')
    def api_status():
        with job_registry_lock:
            jobs = list(JOB_REGISTRY.values())
        jobs.sort(key=lambda j: j.get('created') or '', reverse=True)
        return jsonify({'jobs': jobs})

    @app.route('/api/profiles', methods=['POST'])
    def api_profiles():
        data     = request.get_json(silent=True) or {}
        action   = data.get('action', '')
        name     = (data.get('name') or '').strip()
        config   = load_config()
        profiles = config.get('profiles') or {}

        if action == 'create':
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._-]{0,31}', name) or name.endswith('.failed'):
                return jsonify({'error': 'Names can use letters, numbers, spaces and . _ - (up to 32 characters, no leading dot)'}), 400
            if name in profiles:
                return jsonify({'error': f'Profile "{name}" already exists'}), 409
            in_dir = os.path.join(COMICS_IN, name)
            if os.path.isfile(in_dir) or (os.path.isdir(in_dir) and os.listdir(in_dir)):
                return jsonify({'error': f'"{name}" already exists in Comics_in and is not empty — move it aside or pick another name'}), 409
            profiles[name] = {k: config[k] for k in KCC_KEYS if k in config}
            config['profiles'] = profiles
            save_config(config)
            os.makedirs(in_dir, exist_ok=True)
            os.makedirs(os.path.join(COMICS_OUT, name), exist_ok=True)
            log(f">>> Profile created: {name} — drop comics into /Comics_in/{name}")
            return jsonify({'ok': True})

        if action == 'delete':
            if name not in profiles:
                return jsonify({'error': 'unknown profile'}), 404
            profiles.pop(name)
            config['profiles'] = profiles
            save_config(config)
            log(f">>> Profile deleted: {name} — /Comics_in/{name} now converts with the main settings")
            return jsonify({'ok': True})

        return jsonify({'error': 'unknown action'}), 400

    @app.route('/api/retry', methods=['POST'])
    def api_retry():
        data   = request.get_json(silent=True) or {}
        job_id = data.get('job_id', '')
        if not job_id:
            return jsonify({'error': 'missing job_id'}), 400
        ok = retry_file(job_id)
        return jsonify({'ok': ok})

    @app.route('/api/files')
    def api_files():
        result = {}
        for folder_name, base in (('books', BOOKS_OUT), ('comics', COMICS_OUT)):
            entries: list[dict] = []
            if os.path.isdir(base):
                for root, _, files in os.walk(base):
                    for f in sorted(files):
                        full = os.path.join(root, f)
                        rel  = os.path.relpath(full, base)
                        try:
                            stat = os.stat(full)
                            entries.append({
                                'name':  rel,
                                'size':  stat.st_size,
                                'mtime': datetime.fromtimestamp(
                                    stat.st_mtime, tz=timezone.utc
                                ).strftime('%Y-%m-%dT%H:%M:%SZ'),
                            })
                        except OSError:
                            pass
            entries.sort(key=lambda x: x['mtime'], reverse=True)
            result[folder_name] = entries
        return jsonify(result)

    @app.route('/api/files/download')
    def api_files_download():
        folder  = request.args.get('folder', '')
        name    = request.args.get('name', '')
        allowed = {'books': BOOKS_OUT, 'comics': COMICS_OUT}
        if folder not in allowed or not name:
            return jsonify({'error': 'invalid request'}), 400
        base     = os.path.realpath(allowed[folder])
        filepath = os.path.realpath(os.path.join(base, name))
        if not filepath.startswith(base + os.sep):
            return jsonify({'error': 'invalid path'}), 400
        if not os.path.isfile(filepath):
            return jsonify({'error': 'not found'}), 404
        return send_file(filepath, as_attachment=True,
                         download_name=os.path.basename(filepath))

    @app.route('/api/restart', methods=['POST'])
    def api_restart():
        def _shutdown() -> None:
            time.sleep(0.5)
            os.kill(os.getpid(), signal.SIGTERM)
        threading.Thread(target=_shutdown, daemon=True).start()
        return jsonify({'status': 'restarting'})

    @app.route('/', methods=['GET', 'POST'])
    def index():
        config = load_config()
        saved  = False
        if request.method == 'POST':
            for key in ('kcc_profile', 'kcc_format', 'kcc_cropping', 'kcc_croppingpower',
                        'kcc_croppingminimum', 'kcc_splitter', 'kcc_gamma', 'kcc_batchsplit',
                        'kcc_borders', 'kcc_author', 'kcc_customwidth', 'kcc_customheight'):
                config[key] = request.form.get(key, DEFAULT_CONFIG.get(key, ''))
            for key in ('kcc_manga_style', 'kcc_hq', 'kcc_two_panel', 'kcc_webtoon',
                        'kcc_forcecolor', 'kcc_colorautocontrast', 'kcc_colorcurve',
                        'kcc_eraserainbow', 'kcc_mozjpeg',
                        'kcc_stretch', 'kcc_upscale', 'kcc_nosplitrotate', 'kcc_rotate',
                        'kcc_metadatatitle', 'kcc_nokepub',
                        'notify_on_success', 'notify_on_failure',
                        'preserve_originals', 'bundle_chapter_folders'):
                config[key] = key in request.form
            config['file_wait_timeout'] = request.form.get(
                'file_wait_timeout', DEFAULT_CONFIG.get('file_wait_timeout', 60))
            config['watcher_mode']  = request.form.get('watcher_mode', 'poll')
            config['apprise_urls']  = request.form.get('apprise_urls', '')
            config = _validate_post(config)

            # When a device profile is being edited, its KCC values land in the
            # profile; everything else (watcher, notifications, folder handling)
            # is shared and saves globally either way.
            editing = (request.form.get('editing_profile') or '').strip()
            if editing:
                # If the profile vanished (deleted in another tab), its KCC
                # values are dropped rather than written over the main ones.
                disk     = load_config()
                profiles = disk.get('profiles') or {}
                if editing in profiles:
                    profiles[editing] = {k: config[k] for k in KCC_KEYS if k in config}
                    disk['profiles']  = profiles
                for k, v in config.items():
                    if k not in KCC_KEYS and k != 'profiles':
                        disk[k] = v
                config = disk
            save_config(config)
            saved = True
            do_restart = bool(request.form.get('do_restart'))
            if do_restart:
                def _shutdown() -> None:
                    time.sleep(0.8)
                    os.kill(os.getpid(), signal.SIGTERM)
                threading.Thread(target=_shutdown, daemon=True).start()
                with log_lock:
                    logs = list(LOG_BUFFER)
                return render_template('index.html', config=config, saved=saved,
                                       logs=logs, version=VERSION, restarting=True,
                                       kcc_values={k: config[k] for k in KCC_KEYS},
                                       profiles=config.get('profiles') or {})

        with log_lock:
            logs = list(LOG_BUFFER)

        return render_template('index.html', config=config, saved=saved, logs=logs, version=VERSION,
                               kcc_values={k: config[k] for k in KCC_KEYS},
                               profiles=config.get('profiles') or {})

    # WARNING: do not add --preload to gunicorn. These threads must start in the
    # worker process after fork. --preload would start them in the master process,
    # they would be killed on fork, and the worker would run with dead watchers.
    if start_threads:
        _load_log_history()
        _load_job_registry()
        _mode = load_config().get('watcher_mode', 'poll')
        if _mode == 'inotify':
            log(">>> Bindery started. Watching /Books_in, /Comics_in, and /Comics_raw via inotify.")
            threading.Thread(target=inotify_watch_loop,     daemon=True).start()
            threading.Thread(target=raw_inotify_watch_loop, daemon=True).start()
        else:
            log(">>> Bindery started. Watching /Books_in, /Comics_in, and /Comics_raw every 10s.")
            threading.Thread(target=watch_loop,     daemon=True).start()
            threading.Thread(target=raw_watch_loop, daemon=True).start()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
