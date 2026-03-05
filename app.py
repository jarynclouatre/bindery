import os
import time
import subprocess
import json
import shutil
import threading
import sys
from collections import deque
from flask import Flask, request, render_template_string

app = Flask(__name__)

CONFIG_DIR = '/app/config'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')
COMICS_IN  = '/Comics_in'
COMICS_OUT = '/Comics_out'
BOOKS_IN   = '/Books_in'
BOOKS_OUT  = '/Books_out'

DEFAULT_CONFIG = {
    'kcc_profile':           'KoLC',
    'kcc_format':            'EPUB',
    'kcc_manga_style':       False,
    'kcc_hq':                False,
    'kcc_stretch':           True,
    'kcc_forcecolor':        True,
    'kcc_blackborders':      True,
    'kcc_colorautocontrast': True,
    'kcc_upscale':           False,
    'kcc_metadatatitle':     True,
    'kcc_cropping':          '2',
    'kcc_splitter':          '2',
    'kcc_gamma':             'auto',
}

PROCESSING_LOCKS = set()
lock_mutex       = threading.Lock()
LOG_BUFFER       = deque(maxlen=200)
log_lock         = threading.Lock()

# ── logging ──────────────────────────────────────────────────────────────────

def log(msg):
    line = msg.rstrip()
    with log_lock:
        LOG_BUFFER.append(line)
    sys.stdout.write(line + '\n')
    sys.stdout.flush()

# ── config ───────────────────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in config:
                    config[k] = v
            return config
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

# ── HTML ──────────────────────────────────────────────────────────────────────

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>E-Reader Converter</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #141414; color: #e0e0e0; padding: 24px 16px;
        }
        .wrap { max-width: 860px; margin: auto; }
        h1 { font-size: 1.4rem; color: #5aabff; margin-bottom: 20px; }
        h2 { font-size: 1rem; color: #5aabff; border-bottom: 1px solid #333;
             padding-bottom: 8px; margin: 24px 0 16px; }
        .card { background: #1e1e1e; border: 1px solid #2e2e2e; border-radius: 8px;
                padding: 24px; margin-bottom: 20px; }
        .alert { background: #1a3a1a; border: 1px solid #2a6a2a; color: #6fcf6f;
                 border-radius: 6px; padding: 10px 14px; margin-bottom: 18px; font-size:.9rem; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
        .field { display: flex; flex-direction: column; gap: 5px; margin-bottom: 14px; }
        label { font-size: .83rem; font-weight: 600; color: #aaa; text-transform: uppercase;
                letter-spacing: .04em; }
        select, input[type="text"] {
            padding: 8px 10px; background: #2a2a2a; border: 1px solid #444;
            border-radius: 5px; color: #fff; font-size: .9rem; width: 100%;
        }
        select:focus, input[type="text"]:focus { outline: none; border-color: #5aabff; }
        .checks { display: flex; flex-direction: column; gap: 10px; }
        .check { display: flex; align-items: center; gap: 10px; cursor: pointer; }
        .check input { width: 16px; height: 16px; accent-color: #5aabff; cursor: pointer; }
        .check span { font-size: .9rem; color: #ccc; }
        .check .hint { font-size: .78rem; color: #666; margin-top: 1px; }
        .btn {
            display: block; width: 100%; padding: 12px; margin-top: 22px;
            background: #5aabff; color: #111; border: none; border-radius: 6px;
            font-size: 1rem; font-weight: 700; cursor: pointer; transition: background .15s;
        }
        .btn:hover { background: #3d8fe0; }
        optgroup { background: #1e1e1e; color: #5aabff; }
        option   { background: #2a2a2a; color: #fff; }
        /* log panel */
        .logbox {
            background: #0d0d0d; border: 1px solid #2a2a2a; border-radius: 6px;
            padding: 14px; font-family: monospace; font-size: .78rem; color: #7ec77e;
            height: 260px; overflow-y: auto; white-space: pre-wrap; word-break: break-all;
        }
        .log-err  { color: #e07070; }
        .log-info { color: #7ec77e; }
        .log-warn { color: #e0c060; }
    </style>
</head>
<body>
<div class="wrap">
    <h1>⚡ E-Reader Converter</h1>

    {% if saved %}<div class="alert">✔ Settings saved.</div>{% endif %}

    <div class="card">
        <h2>KCC — Kindle Comic Converter</h2>
        <form method="POST">
        <div class="grid">
            <!-- left column -->
            <div>
                <div class="field">
                    <label>Device Profile</label>
                    <select name="kcc_profile">
                        <optgroup label="─── Kindle ───">
                            {% for val, lbl in [
                                ('K1','Kindle 1'),('K2','Kindle 2'),
                                ('K34','Kindle Keyboard / Touch'),
                                ('K578','Kindle (7th / 8th / 10th gen)'),
                                ('KPW','Kindle Paperwhite 1 / 2'),
                                ('KPW3','Kindle Paperwhite 3 / 4'),
                                ('KPW5','Kindle Paperwhite 5 / Signature'),
                                ('KV','Kindle Voyage'),
                                ('KO','Kindle Oasis 2 / 3'),
                                ('KS','Kindle Scribe'),
                                ('KDX','Kindle DX / DXG'),
                            ] %}
                            <option value="{{ val }}" {% if config.kcc_profile == val %}selected{% endif %}>{{ lbl }}</option>
                            {% endfor %}
                        </optgroup>
                        <optgroup label="─── Kobo ───">
                            {% for val, lbl in [
                                ('KoM','Kobo Mini'),('KoT','Kobo Touch'),
                                ('KoG','Kobo Glo'),('KoGHD','Kobo Glo HD'),
                                ('KoA','Kobo Aura'),('KoAHD','Kobo Aura HD'),
                                ('KoAH2O','Kobo Aura H2O'),('KoAO','Kobo Aura ONE'),
                                ('KoF','Kobo Forma'),('KoC','Kobo Clara HD / 2E'),
                                ('KoCE','Kobo Clara Colour'),
                                ('KoL','Kobo Libra H2O / 2'),
                                ('KoLC','Kobo Libra Colour'),
                                ('KoE','Kobo Elipsa'),('KoE2','Kobo Elipsa 2E'),
                            ] %}
                            <option value="{{ val }}" {% if config.kcc_profile == val %}selected{% endif %}>{{ lbl }}</option>
                            {% endfor %}
                        </optgroup>
                        <optgroup label="─── Other ───">
                            <option value="RM"    {% if config.kcc_profile == 'RM'    %}selected{% endif %}>reMarkable 1 / 2</option>
                            <option value="OTHER" {% if config.kcc_profile == 'OTHER' %}selected{% endif %}>Generic / Custom</option>
                        </optgroup>
                    </select>
                </div>

                <div class="field">
                    <label>Output Format</label>
                    <select name="kcc_format">
                        {% for val, lbl in [('EPUB','EPUB'),('MOBI','MOBI'),('CBZ','CBZ'),('KFX','KFX')] %}
                        <option value="{{ val }}" {% if config.kcc_format == val %}selected{% endif %}>{{ lbl }}</option>
                        {% endfor %}
                    </select>
                </div>

                <div class="field">
                    <label>Cropping</label>
                    <select name="kcc_cropping">
                        <option value="0" {% if config.kcc_cropping == '0' %}selected{% endif %}>Disabled</option>
                        <option value="1" {% if config.kcc_cropping == '1' %}selected{% endif %}>Margins only</option>
                        <option value="2" {% if config.kcc_cropping == '2' %}selected{% endif %}>Margins + Page numbers</option>
                    </select>
                </div>

                <div class="field">
                    <label>Splitter (Landscape pages)</label>
                    <select name="kcc_splitter">
                        <option value="0" {% if config.kcc_splitter == '0' %}selected{% endif %}>Disabled</option>
                        <option value="1" {% if config.kcc_splitter == '1' %}selected{% endif %}>Split left then right</option>
                        <option value="2" {% if config.kcc_splitter == '2' %}selected{% endif %}>Split right then left (manga)</option>
                        <option value="3" {% if config.kcc_splitter == '3' %}selected{% endif %}>Split left only</option>
                        <option value="4" {% if config.kcc_splitter == '4' %}selected{% endif %}>Split right only</option>
                    </select>
                </div>

                <div class="field">
                    <label>Gamma</label>
                    <select name="kcc_gamma">
                        <option value="auto" {% if config.kcc_gamma == 'auto' %}selected{% endif %}>Auto (recommended)</option>
                        {% for v in ['0.5','0.8','1.0','1.2','1.5','1.8','2.0','2.2'] %}
                        <option value="{{ v }}" {% if config.kcc_gamma == v %}selected{% endif %}>{{ v }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>

            <!-- right column: toggles -->
            <div>
                <label style="display:block; margin-bottom:12px;">Options</label>
                <div class="checks">
                    {% set toggles = [
                        ('kcc_manga_style', 'Manga Style',         'Right-to-left page order'),
                        ('kcc_hq',          'High Quality',         'Slower but better output'),
                        ('kcc_stretch',     'Stretch',              'Fill screen, ignore aspect ratio'),
                        ('kcc_forcecolor',  'Force Color',          'Keep color even on grayscale devices'),
                        ('kcc_blackborders','Black Borders',        'Add black bars instead of white'),
                        ('kcc_colorautocontrast', 'Auto-Contrast',  'Boost color image contrast'),
                        ('kcc_upscale',     'Upscale',              'Upscale images smaller than screen'),
                        ('kcc_metadatatitle','Use Filename as Title','Sets EPUB metadata title from filename'),
                    ] %}
                    {% for key, lbl, hint in toggles %}
                    <label class="check">
                        <input type="checkbox" name="{{ key }}" {% if config[key] %}checked{% endif %}>
                        <span>{{ lbl }}<br><span class="hint">{{ hint }}</span></span>
                    </label>
                    {% endfor %}
                </div>
            </div>
        </div>
        <button type="submit" class="btn">Save Configuration</button>
        </form>
    </div>

    <!-- Live log panel -->
    <div class="card">
        <h2>Recent Activity</h2>
        <div class="logbox" id="logbox">
        {% for line in logs %}
            {% if 'FAILED' in line or 'ERROR' in line %}<span class="log-err">{{ line }}</span>
            {% elif 'SUCCESS' in line or 'STARTING' in line %}<span class="log-info">{{ line }}</span>
            {% else %}<span class="log-warn">{{ line }}</span>
            {% endif %}
        {% endfor %}
        </div>
    </div>
</div>
<script>
    // Auto-scroll log to bottom on load
    var lb = document.getElementById('logbox');
    lb.scrollTop = lb.scrollHeight;
    // Auto-refresh log every 8 seconds
    setInterval(function(){ location.reload(); }, 8000);
</script>
</body>
</html>
"""

# ── routes ────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET', 'POST'])
def index():
    config = load_config()
    saved  = False
    if request.method == 'POST':
        config['kcc_profile']           = request.form.get('kcc_profile', 'KoLC')
        config['kcc_format']            = request.form.get('kcc_format', 'EPUB')
        config['kcc_cropping']          = request.form.get('kcc_cropping', '2')
        config['kcc_splitter']          = request.form.get('kcc_splitter', '2')
        config['kcc_gamma']             = request.form.get('kcc_gamma', 'auto')
        config['kcc_manga_style']       = 'kcc_manga_style'       in request.form
        config['kcc_hq']                = 'kcc_hq'                in request.form
        config['kcc_stretch']           = 'kcc_stretch'           in request.form
        config['kcc_forcecolor']        = 'kcc_forcecolor'        in request.form
        config['kcc_blackborders']      = 'kcc_blackborders'      in request.form
        config['kcc_colorautocontrast'] = 'kcc_colorautocontrast' in request.form
        config['kcc_upscale']           = 'kcc_upscale'           in request.form
        config['kcc_metadatatitle']     = 'kcc_metadatatitle'     in request.form
        save_config(config)
        saved = True

    with log_lock:
        logs = list(LOG_BUFFER)

    return render_template_string(HTML_TEMPLATE, config=config, saved=saved, logs=logs)

# ── file helpers ──────────────────────────────────────────────────────────────

def wait_for_file_ready(filepath):
    """Poll until file size is stable for two consecutive checks."""
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

def get_newest_file(directory):
    files = [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
    ]
    return max(files, key=os.path.getmtime) if files else None

def handle_output_renaming(produced_file, target_dir, original_input, c_type):
    """
    Move produced_file into target_dir.
    - .kepub.epub → .kepub  (both kepubify books and KCC Kobo comics)
    - All other extensions  → kept as-is (Kindle EPUB, MOBI, CBZ, …)
    """
    if not produced_file:
        return False
    filename = os.path.basename(produced_file)
    if filename.endswith('.kepub.epub'):
        filename = filename[:-len('.kepub.epub')] + '.kepub'
    # Any other extension (plain .epub for Kindle, .mobi, .cbz) is left unchanged.
    os.makedirs(target_dir, exist_ok=True)
    final_path = os.path.join(target_dir, filename)
    shutil.move(produced_file, final_path)
    if os.path.exists(original_input):
        os.remove(original_input)
    return True

# ── core processing ───────────────────────────────────────────────────────────

def process_file(filepath, c_type):
    short = os.path.basename(filepath)[:20]
    try:
        if not wait_for_file_ready(filepath):
            log(f">>> SKIP (not ready): {short}")
            return

        config  = load_config()
        in_base = BOOKS_IN if c_type == 'book' else COMICS_IN
        rel_dir = os.path.dirname(os.path.relpath(filepath, in_base))
        if rel_dir == '.':
            rel_dir = ''
        out_base   = BOOKS_OUT if c_type == 'book' else COMICS_OUT
        target_dir = os.path.join(out_base, rel_dir)
        temp_out   = os.path.join('/tmp', os.path.basename(filepath) + '_out')
        os.makedirs(temp_out, exist_ok=True)

        if c_type == 'book':
            log(f">>> STARTING: kepubify on {short}")
            cmd = [
                'kepubify',
                '--calibre',
                '--inplace',
                '--output', temp_out,
                filepath,
            ]
        else:
            log(f">>> STARTING: KCC on {short}")
            # ── Build KCC command ──────────────────────────────────────────
            # All flags MUST come before the positional input path.
            # --title requires a string value; pass the filename stem.
            cmd = [
                'kcc-c2e',
                '--profile',  config['kcc_profile'],
                '--format',   config['kcc_format'],
                '--splitter', config['kcc_splitter'],
                '--cropping', config['kcc_cropping'],
                '--output',   temp_out,
            ]
            if config['kcc_manga_style']:       cmd.append('--manga-style')
            if config['kcc_hq']:                cmd.append('--hq')
            if config['kcc_stretch']:           cmd.append('--stretch')
            if config['kcc_forcecolor']:        cmd.append('--forcecolor')
            if config['kcc_blackborders']:      cmd.append('--blackborders')
            if config['kcc_colorautocontrast']: cmd.append('--colorautocontrast')
            if config['kcc_upscale']:           cmd.append('--upscale')
            if config['kcc_metadatatitle']:
                # Extract filename without extension as the EPUB title.
                title = os.path.splitext(os.path.basename(filepath))[0]
                cmd.extend(['--title', title])          # ← FIX: value required
            if config.get('kcc_gamma', 'auto').lower() != 'auto':
                cmd.extend(['--gamma', config['kcc_gamma']])
            cmd.append(filepath)                        # positional LAST
            # ──────────────────────────────────────────────────────────────

        log(f">>> CMD: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # merge stderr into stdout stream
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            log(f"[{short}] {line.rstrip()}")
        process.wait()

        if process.returncode == 0:
            produced = get_newest_file(temp_out)
            if handle_output_renaming(produced, target_dir, filepath, c_type):
                log(f">>> SUCCESS: {short}")
            else:
                log(f">>> FAILED (no output file found): {short}")
        else:
            log(f">>> FAILED (exit {process.returncode}): {short}")
            if os.path.exists(filepath):
                os.rename(filepath, filepath + '.failed')

    except Exception as e:
        log(f">>> ERROR: {short} — {e}")
    finally:
        if os.path.exists(temp_out):
            shutil.rmtree(temp_out, ignore_errors=True)
        with lock_mutex:
            PROCESSING_LOCKS.discard(filepath)

# ── scanner ───────────────────────────────────────────────────────────────────

BOOK_EXTS  = {'.epub', '.kepub'}
COMIC_EXTS = {'.cbz', '.cbr', '.zip', '.rar'}

def scan_directories():
    for root, _, files in os.walk(BOOKS_IN):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in BOOK_EXTS and not f.endswith('.failed'):
                path = os.path.join(root, f)
                with lock_mutex:
                    if path not in PROCESSING_LOCKS:
                        PROCESSING_LOCKS.add(path)
                        threading.Thread(
                            target=process_file, args=(path, 'book'), daemon=True
                        ).start()

    for root, _, files in os.walk(COMICS_IN):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in COMIC_EXTS and not f.endswith('.failed'):
                path = os.path.join(root, f)
                with lock_mutex:
                    if path not in PROCESSING_LOCKS:
                        PROCESSING_LOCKS.add(path)
                        threading.Thread(
                            target=process_file, args=(path, 'comic'), daemon=True
                        ).start()

def watch_loop():
    while True:
        try:
            scan_directories()
        except Exception as e:
            log(f">>> SCAN ERROR: {e}")
        time.sleep(10)

# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    log(">>> Converter started. Watching /Books_in and /Comics_in every 10s.")
    threading.Thread(target=watch_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)
