import os
import time
import subprocess
import json
import shutil
import threading
import sys
import uuid
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
    'kcc_manga_style':       False,
    'kcc_hq':                False,
    'kcc_two_panel':         False,
    'kcc_webtoon':           False,
    'kcc_blackborders':      True,
    'kcc_whiteborders':      False,
    'kcc_forcecolor':        True,
    'kcc_colorautocontrast': True,
    'kcc_colorcurve':        False,
    'kcc_stretch':           True,
    'kcc_upscale':           False,
    'kcc_nosplitrotate':     False,
    'kcc_rotate':            False,
    'kcc_cropping':          '2',
    'kcc_croppingpower':     '1.0',
    'kcc_croppingminimum':   '1',
    'kcc_splitter':          '1',
    'kcc_gamma':             '0',
    'kcc_format':            'EPUB',
    'kcc_nokepub':           False,
    'kcc_metadatatitle':     True,
    'kcc_author':            '',
    'kcc_batchsplit':        '0',
    'kcc_customwidth':       '',
    'kcc_customheight':      '',
}

PROCESSING_LOCKS = set()
lock_mutex       = threading.Lock()
LOG_BUFFER       = deque(maxlen=300)
log_lock         = threading.Lock()

def log(msg):
    line = msg.rstrip()
    with log_lock:
        LOG_BUFFER.append(line)
    sys.stdout.write(line + '\n')
    sys.stdout.flush()

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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Bindery</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #141414; color: #e0e0e0; padding: 24px 16px;
        }
        .wrap { max-width: 980px; margin: auto; }
        h1 { font-size: 1.5rem; color: #5aabff; margin-bottom: 4px; }
        .subtitle { font-size: .85rem; color: #555; margin-bottom: 24px; }
        h2 { font-size: .82rem; color: #5aabff; border-bottom: 1px solid #252525;
             padding-bottom: 8px; margin: 0 0 16px; text-transform: uppercase;
             letter-spacing: .07em; }
        .card { background: #1c1c1c; border: 1px solid #282828; border-radius: 8px;
                padding: 22px; margin-bottom: 20px; }
        .alert { background: #182818; border: 1px solid #2a5a2a; color: #6fcf6f;
                 border-radius: 6px; padding: 10px 14px; margin-bottom: 18px;
                 font-size: .88rem; }
        .grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 24px; }
        @media (max-width: 760px) { .grid-3 { grid-template-columns: 1fr; } }
        .field { margin-bottom: 14px; }
        .field:last-child { margin-bottom: 0; }
        label.lbl { display: block; font-size: .73rem; font-weight: 700; color: #666;
                    text-transform: uppercase; letter-spacing: .06em; margin-bottom: 5px; }
        select, input[type="text"], input[type="number"] {
            width: 100%; padding: 8px 10px; background: #222; border: 1px solid #363636;
            border-radius: 5px; color: #e0e0e0; font-size: .88rem; appearance: auto;
        }
        select:focus, input:focus { outline: none; border-color: #5aabff; }
        .sec { font-size: .7rem; font-weight: 700; color: #444; text-transform: uppercase;
               letter-spacing: .08em; margin: 18px 0 10px;
               padding-top: 14px; border-top: 1px solid #252525; }
        .sec:first-child { margin-top: 0; padding-top: 0; border-top: none; }
        .checks { display: flex; flex-direction: column; gap: 4px; }
        .check { display: flex; align-items: flex-start; gap: 10px;
                 padding: 7px 8px; border-radius: 5px; cursor: pointer;
                 transition: background .12s; }
        .check:hover { background: #222; }
        .check input[type="checkbox"] {
            width: 15px; height: 15px; margin-top: 2px;
            accent-color: #5aabff; cursor: pointer; flex-shrink: 0;
        }
        .check-label { font-size: .88rem; color: #d8d8d8; line-height: 1.3; }
        .check-hint  { font-size: .74rem; color: #4a4a4a; margin-top: 2px; }
        .btn { display: block; width: 100%; padding: 13px; margin-top: 22px;
               background: #5aabff; color: #0a0a0a; border: none; border-radius: 6px;
               font-size: .95rem; font-weight: 700; cursor: pointer;
               transition: background .15s; letter-spacing: .02em; }
        .btn:hover { background: #3d8fe0; }
        .log-header { display: flex; justify-content: space-between;
                      align-items: center; margin-bottom: 12px; }
        .log-refresh { color: #5aabff; text-decoration: none; font-size: .8rem; }
        .log-refresh:hover { text-decoration: underline; }
        .logbox { background: #0d0d0d; border: 1px solid #1e1e1e; border-radius: 6px;
                  padding: 14px; font-family: "SF Mono", "Fira Mono", monospace;
                  font-size: .74rem; height: 280px; overflow-y: auto;
                  white-space: pre-wrap; word-break: break-all; }
        .log-ok   { color: #5db85d; }
        .log-err  { color: #c96060; }
        .log-cmd  { color: #4a4a4a; }
        .log-info { color: #a0a0a0; }
        .note { font-size: .74rem; color: #444; margin-bottom: 10px; line-height: 1.5; }
        optgroup { background: #1c1c1c; }
        option   { background: #222; color: #e0e0e0; }
    </style>
</head>
<body>
<div class="wrap">

    <h1>Bindery</h1>
    <p class="subtitle">Automated e-book and comic converter — scanning every 10 seconds</p>

    {% if saved %}<div class="alert">Settings saved successfully.</div>{% endif %}

    <form method="POST">
    <div class="card">
        <h2>KCC — Kindle Comic Converter</h2>
        <div class="grid-3">

            <div>
                <div class="sec">Device and Output</div>

                <div class="field">
                    <label class="lbl">Device Profile</label>
                    <select name="kcc_profile">
                        <optgroup label="Kindle">
                            {% for val, lbl in [
                                ('K1','Kindle 1'),
                                ('K2','Kindle 2'),
                                ('K34','Kindle Keyboard / Touch'),
                                ('K578','Kindle 7th / 8th / 10th gen'),
                                ('KPW','Kindle Paperwhite 1 / 2'),
                                ('KPW3','Kindle Paperwhite 3 / 4'),
                                ('KPW5','Kindle Paperwhite 5 / Signature'),
                                ('KV','Kindle Voyage'),
                                ('KO','Kindle Oasis 2 / 3'),
                                ('KS','Kindle Scribe'),
                                ('KDX','Kindle DX / DXG')
                            ] %}
                            <option value="{{ val }}" {% if config.kcc_profile == val %}selected{% endif %}>{{ lbl }}</option>
                            {% endfor %}
                        </optgroup>
                        <optgroup label="Kobo">
                            {% for val, lbl in [
                                ('KoM','Kobo Mini'),
                                ('KoT','Kobo Touch'),
                                ('KoG','Kobo Glo'),
                                ('KoGHD','Kobo Glo HD'),
                                ('KoA','Kobo Aura'),
                                ('KoAHD','Kobo Aura HD'),
                                ('KoAH2O','Kobo Aura H2O'),
                                ('KoAO','Kobo Aura ONE'),
                                ('KoF','Kobo Forma'),
                                ('KoC','Kobo Clara HD / 2E'),
                                ('KoCE','Kobo Clara Colour'),
                                ('KoL','Kobo Libra H2O / 2'),
                                ('KoLC','Kobo Libra Colour'),
                                ('KoE','Kobo Elipsa'),
                                ('KoE2','Kobo Elipsa 2E')
                            ] %}
                            <option value="{{ val }}" {% if config.kcc_profile == val %}selected{% endif %}>{{ lbl }}</option>
                            {% endfor %}
                        </optgroup>
                        <optgroup label="reMarkable">
                            <option value="Rmk1"  {% if config.kcc_profile == 'Rmk1'  %}selected{% endif %}>reMarkable 1</option>
                            <option value="Rmk2"  {% if config.kcc_profile == 'Rmk2'  %}selected{% endif %}>reMarkable 2</option>
                            <option value="RmkPP" {% if config.kcc_profile == 'RmkPP' %}selected{% endif %}>reMarkable Paper Pro</option>
                        </optgroup>
                        <optgroup label="Other">
                            <option value="OTHER" {% if config.kcc_profile == 'OTHER' %}selected{% endif %}>Generic / Custom resolution</option>
                        </optgroup>
                    </select>
                </div>

                <div class="field">
                    <label class="lbl">Output Format</label>
                    <select name="kcc_format">
                        <option value="EPUB" {% if config.kcc_format == 'EPUB' %}selected{% endif %}>EPUB</option>
                        <option value="MOBI" {% if config.kcc_format == 'MOBI' %}selected{% endif %}>MOBI</option>
                        <option value="CBZ"  {% if config.kcc_format == 'CBZ'  %}selected{% endif %}>CBZ</option>
                        <option value="KFX"  {% if config.kcc_format == 'KFX'  %}selected{% endif %}>KFX</option>
                    </select>
                </div>

                <div class="field">
                    <label class="lbl">Batch Split</label>
                    <select name="kcc_batchsplit">
                        <option value="0" {% if config.kcc_batchsplit == '0' %}selected{% endif %}>Disabled</option>
                        <option value="1" {% if config.kcc_batchsplit == '1' %}selected{% endif %}>Split into volumes</option>
                        <option value="2" {% if config.kcc_batchsplit == '2' %}selected{% endif %}>Split into chapters</option>
                    </select>
                </div>

                <div class="sec">Image Processing</div>

                <div class="field">
                    <label class="lbl">Cropping</label>
                    <select name="kcc_cropping">
                        <option value="0" {% if config.kcc_cropping == '0' %}selected{% endif %}>Disabled</option>
                        <option value="1" {% if config.kcc_cropping == '1' %}selected{% endif %}>Margins only</option>
                        <option value="2" {% if config.kcc_cropping == '2' %}selected{% endif %}>Margins + page numbers</option>
                    </select>
                </div>

                <div class="field">
                    <label class="lbl">Cropping Power</label>
                    <input type="number" name="kcc_croppingpower"
                           step="0.1" min="0.1" max="2.0"
                           value="{{ config.kcc_croppingpower }}">
                </div>

                <div class="field">
                    <label class="lbl">Cropping Minimum (%)</label>
                    <input type="number" name="kcc_croppingminimum"
                           step="1" min="0" max="50"
                           value="{{ config.kcc_croppingminimum }}">
                </div>

                <div class="field">
                    <label class="lbl">Splitter (Landscape pages)</label>
                    <select name="kcc_splitter">
                        <option value="0" {% if config.kcc_splitter == '0' %}selected{% endif %}>Disabled</option>
                        <option value="1" {% if config.kcc_splitter == '1' %}selected{% endif %}>Left then right</option>
                        <option value="2" {% if config.kcc_splitter == '2' %}selected{% endif %}>Right then left</option>
                        <option value="3" {% if config.kcc_splitter == '3' %}selected{% endif %}>Left page only</option>
                        <option value="4" {% if config.kcc_splitter == '4' %}selected{% endif %}>Right page only</option>
                    </select>
                </div>

                <div class="field">
                    <label class="lbl">Gamma</label>
                    <select name="kcc_gamma">
                        <option value="0"   {% if config.kcc_gamma == '0'   %}selected{% endif %}>Auto (KCC default)</option>
                        <option value="0.5" {% if config.kcc_gamma == '0.5' %}selected{% endif %}>0.5</option>
                        <option value="0.8" {% if config.kcc_gamma == '0.8' %}selected{% endif %}>0.8</option>
                        <option value="1.0" {% if config.kcc_gamma == '1.0' %}selected{% endif %}>1.0 — No correction</option>
                        <option value="1.2" {% if config.kcc_gamma == '1.2' %}selected{% endif %}>1.2</option>
                        <option value="1.5" {% if config.kcc_gamma == '1.5' %}selected{% endif %}>1.5</option>
                        <option value="1.8" {% if config.kcc_gamma == '1.8' %}selected{% endif %}>1.8</option>
                        <option value="2.0" {% if config.kcc_gamma == '2.0' %}selected{% endif %}>2.0</option>
                        <option value="2.2" {% if config.kcc_gamma == '2.2' %}selected{% endif %}>2.2</option>
                    </select>
                </div>
            </div>

            <div>
                <div class="sec">Page Layout</div>
                <div class="checks">
                    <label class="check">
                        <input type="checkbox" name="kcc_manga_style" {% if config.kcc_manga_style %}checked{% endif %}>
                        <span>
                            <div class="check-label">Manga Style</div>
                            <div class="check-hint">Right-to-left page navigation order</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_two_panel" {% if config.kcc_two_panel %}checked{% endif %}>
                        <span>
                            <div class="check-label">Two Panel</div>
                            <div class="check-hint">Treat landscape pages as two-panel spreads</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_webtoon" {% if config.kcc_webtoon %}checked{% endif %}>
                        <span>
                            <div class="check-label">Webtoon</div>
                            <div class="check-hint">Optimise for vertical-strip webtoon format</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_stretch" {% if config.kcc_stretch %}checked{% endif %}>
                        <span>
                            <div class="check-label">Stretch</div>
                            <div class="check-hint">Fill screen, ignoring original aspect ratio</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_upscale" {% if config.kcc_upscale %}checked{% endif %}>
                        <span>
                            <div class="check-label">Upscale</div>
                            <div class="check-hint">Upscale images smaller than the device resolution</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_nosplitrotate" {% if config.kcc_nosplitrotate %}checked{% endif %}>
                        <span>
                            <div class="check-label">No Split / Rotate</div>
                            <div class="check-hint">Disable automatic splitting and rotation of landscape pages</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_rotate" {% if config.kcc_rotate %}checked{% endif %}>
                        <span>
                            <div class="check-label">Rotate</div>
                            <div class="check-hint">Rotate landscape pages instead of splitting them</div>
                        </span>
                    </label>
                </div>

                <div class="sec">Borders</div>
                <div class="checks">
                    <label class="check">
                        <input type="checkbox" name="kcc_blackborders" {% if config.kcc_blackborders %}checked{% endif %}>
                        <span>
                            <div class="check-label">Black Borders</div>
                            <div class="check-hint">Fill unused screen area with black</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_whiteborders" {% if config.kcc_whiteborders %}checked{% endif %}>
                        <span>
                            <div class="check-label">White Borders</div>
                            <div class="check-hint">Fill unused screen area with white (overrides black borders)</div>
                        </span>
                    </label>
                </div>
            </div>

            <div>
                <div class="sec">Color and Quality</div>
                <div class="checks">
                    <label class="check">
                        <input type="checkbox" name="kcc_forcecolor" {% if config.kcc_forcecolor %}checked{% endif %}>
                        <span>
                            <div class="check-label">Force Color</div>
                            <div class="check-hint">Preserve color data even on grayscale device profiles</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_colorautocontrast" {% if config.kcc_colorautocontrast %}checked{% endif %}>
                        <span>
                            <div class="check-label">Auto-Contrast</div>
                            <div class="check-hint">Automatically boost color image contrast</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_colorcurve" {% if config.kcc_colorcurve %}checked{% endif %}>
                        <span>
                            <div class="check-label">Color Curve</div>
                            <div class="check-hint">Apply S-curve color correction to images</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_hq" {% if config.kcc_hq %}checked{% endif %}>
                        <span>
                            <div class="check-label">High Quality</div>
                            <div class="check-hint">Slower processing, marginally better image output</div>
                        </span>
                    </label>
                </div>

                <div class="sec">Output Metadata</div>
                <div class="checks" style="margin-bottom: 14px;">
                    <label class="check">
                        <input type="checkbox" name="kcc_metadatatitle" {% if config.kcc_metadatatitle %}checked{% endif %}>
                        <span>
                            <div class="check-label">Use Filename as Title</div>
                            <div class="check-hint">Sets EPUB metadata title from the source filename</div>
                        </span>
                    </label>
                    <label class="check">
                        <input type="checkbox" name="kcc_nokepub" {% if config.kcc_nokepub %}checked{% endif %}>
                        <span>
                            <div class="check-label">No KEPUB Extension</div>
                            <div class="check-hint">Output .epub instead of .kepub.epub on Kobo profiles</div>
                        </span>
                    </label>
                </div>

                <div class="field">
                    <label class="lbl">Author</label>
                    <input type="text" name="kcc_author"
                           placeholder="Leave blank to use KCC default"
                           value="{{ config.kcc_author }}">
                </div>

                <div class="sec">Custom Profile Resolution</div>
                <p class="note">Only used when profile is set to Generic / Custom.</p>
                <div class="field">
                    <label class="lbl">Custom Width (px)</label>
                    <input type="number" name="kcc_customwidth" min="0"
                           placeholder="e.g. 1264"
                           value="{{ config.kcc_customwidth }}">
                </div>
                <div class="field">
                    <label class="lbl">Custom Height (px)</label>
                    <input type="number" name="kcc_customheight" min="0"
                           placeholder="e.g. 1680"
                           value="{{ config.kcc_customheight }}">
                </div>
            </div>

        </div>

        <button type="submit" class="btn">Save Configuration</button>
    </div>
    </form>

    <div class="card">
        <div class="log-header">
            <h2 style="border:none; margin:0; padding:0;">Recent Activity</h2>
            <a href="/" class="log-refresh">Refresh</a>
        </div>
        <div class="logbox" id="logbox">
{% for line in logs %}{% if 'SUCCESS' in line or 'STARTING' in line %}<span class="log-ok">{{ line }}</span>
{% elif 'FAILED' in line or 'ERROR' in line %}<span class="log-err">{{ line }}</span>
{% elif 'CMD:' in line %}<span class="log-cmd">{{ line }}</span>
{% else %}<span class="log-info">{{ line }}</span>
{% endif %}{% endfor %}
        </div>
    </div>

</div>
<script>
    var lb = document.getElementById('logbox');
    if (lb) lb.scrollTop = lb.scrollHeight;
</script>
</body>
</html>
"""

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

    return render_template_string(HTML_TEMPLATE, config=config, saved=saved, logs=logs)

def wait_for_file_ready(filepath):
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

def prune_empty_dirs(file_path, stop_at):
    d = os.path.dirname(os.path.abspath(file_path))
    stop_at = os.path.abspath(stop_at)
    while d != stop_at and d.startswith(stop_at + os.sep):
        try:
            os.rmdir(d)
            d = os.path.dirname(d)
        except OSError:
            break

def handle_output_renaming(produced_file, target_dir, original_input, in_base):
    if not produced_file:
        return False
    filename = os.path.basename(produced_file)
    if filename.endswith('.kepub.epub'):
        filename = filename[:-len('.kepub.epub')] + '.kepub'
    os.makedirs(target_dir, exist_ok=True)
    final_path = os.path.join(target_dir, filename)
    shutil.move(produced_file, final_path)
    if os.path.exists(original_input):
        os.remove(original_input)
        prune_empty_dirs(original_input, in_base)
    return True

def process_file(filepath, c_type):
    short    = os.path.basename(filepath)[:24]
    in_base  = BOOKS_IN if c_type == 'book' else COMICS_IN
    temp_out = os.path.join('/tmp', os.path.basename(filepath) + '_' + uuid.uuid4().hex + '_out')
    try:
        if not wait_for_file_ready(filepath):
            log(f">>> SKIP (not ready): {short}")
            return

        config  = load_config()
        rel_dir = os.path.dirname(os.path.relpath(filepath, in_base))
        if rel_dir == '.':
            rel_dir = ''
        out_base   = BOOKS_OUT if c_type == 'book' else COMICS_OUT
        target_dir = os.path.join(out_base, rel_dir)
        os.makedirs(temp_out, exist_ok=True)

        if c_type == 'book':
            log(f">>> STARTING: kepubify on {short}")
            cmd = ['kepubify', '--calibre', '--inplace', '--output', temp_out, filepath]

        else:
            log(f">>> STARTING: KCC on {short}")
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

        log(f">>> CMD: {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in process.stdout:
            log(f"[{short}] {line.rstrip()}")
        process.wait()

        if process.returncode == 0:
            produced = get_newest_file(temp_out)
            if handle_output_renaming(produced, target_dir, filepath, in_base):
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
        shutil.rmtree(temp_out, ignore_errors=True)
        with lock_mutex:
            PROCESSING_LOCKS.discard(filepath)

BOOK_EXTS  = {'.epub'}
COMIC_EXTS = {'.cbz', '.cbr', '.zip', '.rar'}

def scan_directories():
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

def watch_loop():
    while True:
        try:
            scan_directories()
        except Exception as e:
            log(f">>> SCAN ERROR: {e}")
        time.sleep(10)

log(">>> Bindery started. Watching /Books_in and /Comics_in every 10s.")
threading.Thread(target=watch_loop, daemon=True).start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True)
