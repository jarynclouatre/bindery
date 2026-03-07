"""Flask application factory, WebUI routes, and form validation."""

import threading
from flask import Flask, jsonify, request, render_template

from config import DEFAULT_CONFIG, load_config, save_config, ConfigDict
from processor import LOG_BUFFER, log_lock, log, watch_loop
from raw_processor import raw_watch_loop

VERSION = "2.7.0"


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
    return config


def create_app(start_threads: bool = True) -> Flask:
    app = Flask(__name__)

    @app.route('/health')
    def health():
        return jsonify({'status': 'ok'})

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
            config = _validate_post(config)
            save_config(config)
            saved = True

        with log_lock:
            logs = list(LOG_BUFFER)

        return render_template('index.html', config=config, saved=saved, logs=logs, version=VERSION)

    # WARNING: do not add --preload to gunicorn. These threads must start in the
    # worker process after fork. --preload would start them in the master process,
    # they would be killed on fork, and the worker would run with dead watchers.
    if start_threads:
        log(">>> Bindery started. Watching /Books_in, /Comics_in, and /Comics_raw every 10s.")
        threading.Thread(target=watch_loop, daemon=True).start()
        threading.Thread(target=raw_watch_loop, daemon=True).start()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
