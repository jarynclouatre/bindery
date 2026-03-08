"""Flask application factory, WebUI routes, and form validation."""

import os
import signal
import time
import threading
from flask import Flask, jsonify, request, render_template

from config import DEFAULT_CONFIG, load_config, save_config, ConfigDict
from processor import LOG_BUFFER, log_lock, log, watch_loop, inotify_watch_loop, _load_log_history
from raw_processor import raw_watch_loop, raw_inotify_watch_loop

VERSION = "2.8.1"


def _clamp(value: object, min_val: float, max_val: float, default: float) -> str:
    """Parse value as float, clamping to [min_val, max_val]. Returns default on invalid input."""
    try:
        return str(max(min_val, min(max_val, float(value))))
    except (ValueError, TypeError):
        return str(default)


def _validate_post(config: ConfigDict) -> ConfigDict:
    """Clamp numeric fields to their valid ranges after reading from the form."""
    config['kcc_croppingpower']   = _clamp(config['kcc_croppingpower'],   0.1, 2.0, 1.0)
    config['kcc_croppingminimum'] = _clamp(config['kcc_croppingminimum'],   0,  50,  1)
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
    _VALID_FORMAT     = {'EPUB', 'MOBI', 'CBZ', 'KFX'}
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

    return config


def create_app(start_threads: bool = True) -> Flask:
    app = Flask(__name__)

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

    @app.route('/api/logs')
    def api_logs():
        with log_lock:
            logs = list(LOG_BUFFER)
        return jsonify({'logs': logs})

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
                        'kcc_forcecolor',
                        'kcc_colorautocontrast', 'kcc_colorcurve', 'kcc_stretch',
                        'kcc_upscale', 'kcc_nosplitrotate', 'kcc_rotate',
                        'kcc_metadatatitle', 'kcc_nokepub'):
                config[key] = key in request.form
            config['file_wait_timeout'] = request.form.get(
                'file_wait_timeout', DEFAULT_CONFIG.get('file_wait_timeout', 60))
            config['watcher_mode'] = request.form.get('watcher_mode', 'poll')
            config = _validate_post(config)
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
                                       logs=logs, version=VERSION, restarting=True)

        with log_lock:
            logs = list(LOG_BUFFER)

        return render_template('index.html', config=config, saved=saved, logs=logs, version=VERSION)

    # WARNING: do not add --preload to gunicorn. These threads must start in the
    # worker process after fork. --preload would start them in the master process,
    # they would be killed on fork, and the worker would run with dead watchers.
    if start_threads:
        _load_log_history()
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
