import threading
from flask import Flask, jsonify, request, render_template

from config import DEFAULT_CONFIG, load_config, save_config
from processor import LOG_BUFFER, log_lock, log, watch_loop
from raw_processor import raw_watch_loop

app = Flask(__name__)
VERSION = "2.2.0"


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
                    'kcc_author', 'kcc_customwidth', 'kcc_customheight'):
            config[key] = request.form.get(key, DEFAULT_CONFIG.get(key, ''))
        for key in ('kcc_manga_style', 'kcc_hq', 'kcc_two_panel', 'kcc_webtoon',
                    'kcc_blackborders', 'kcc_whiteborders', 'kcc_forcecolor',
                    'kcc_colorautocontrast', 'kcc_colorcurve', 'kcc_stretch',
                    'kcc_upscale', 'kcc_nosplitrotate', 'kcc_rotate',
                    'kcc_metadatatitle', 'kcc_nokepub'):
            config[key] = key in request.form
        save_config(config)
        saved = True

    with log_lock:
        logs = list(LOG_BUFFER)

    return render_template('index.html', config=config, saved=saved, logs=logs, version=VERSION)


log(">>> Bindery started. Watching /Books_in, /Comics_in, and /Comics_raw every 10s.")
threading.Thread(target=watch_loop, daemon=True).start()
threading.Thread(target=raw_watch_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
