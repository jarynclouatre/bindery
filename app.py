import os
import time
import subprocess
import json
import shutil
import threading
from flask import Flask, request, render_template_string

app = Flask(__name__)

CONFIG_DIR = '/app/config'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')
COMICS_IN = '/Comics_in'
COMICS_OUT = '/Comics_out'
BOOKS_IN = '/Books_in'
BOOKS_OUT = '/Books_out'

DEFAULT_CONFIG = {
    'kcc_profile': 'KoLC',
    'kcc_format': 'EPUB',
    'kcc_manga_style': False,
    'kcc_hq': False,
    'kcc_stretch': True,
    'kcc_forcecolor': True,
    'kcc_blackborders': True,
    'kcc_colorautocontrast': True,
    'kcc_upscale': False,
    'kcc_metadatatitle': True,
    'kcc_cropping': '2',
    'kcc_splitter': '2',
    'kcc_gamma': 'auto'
}

PROCESSING_LOCKS = set()

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
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG

def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>E-Reader Converter Settings</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; background: #1e1e1e; color: #f0f0f0; }
        .container { background: #2d2d2d; padding: 30px; border-radius: 8px; max-width: 800px; margin: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h2, h3 { color: #4da6ff; border-bottom: 1px solid #444; padding-bottom: 10px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
        .group { display: flex; flex-direction: column; margin-bottom: 15px; }
        .checkbox-group { display: flex; align-items: center; margin-bottom: 15px; }
        .checkbox-group label { margin-left: 10px; margin-bottom: 0; }
        label { font-weight: bold; margin-bottom: 5px; color: #ccc; }
        select, input[type="text"] { padding: 8px; border-radius: 4px; border: 1px solid #555; background: #333; color: #fff; }
        input[type="submit"] { background: #4da6ff; color: #111; border: none; padding: 12px 20px; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; margin-top: 20px; }
        input[type="submit"]:hover { background: #3388dd; }
        .alert { padding: 10px; background: #28a745; color: white; border-radius: 4px; margin-bottom: 20px; }
        optgroup { font-weight: bold; color: #4da6ff; background: #222; }
        option { color: #fff; background: #333; }
    </style>
</head>
<body>
    <div class="container">
        <h2>Global Settings</h2>
        {% if saved %}
        <div class="alert">Settings saved successfully.</div>
        {% endif %}
        <form method="POST">
            <h3>KCC (Kindle Comic Converter)</h3>
            <div class="grid">
                <div>
                    <div class="group">
                        <label>Profile Device</label>
                        <select name="kcc_profile">
                            <optgroup label="Kindle">
                                <option value="K1" {% if config.kcc_profile == 'K1' %}selected{% endif %}>Kindle 1</option>
                                <option value="K2" {% if config.kcc_profile == 'K2' %}selected{% endif %}>Kindle 2</option>
                                <option value="K34" {% if config.kcc_profile == 'K34' %}selected{% endif %}>Kindle Keyboard/Touch</option>
                                <option value="K578" {% if config.kcc_profile == 'K578' %}selected{% endif %}>Kindle</option>
                                <option value="KPW" {% if config.kcc_profile == 'KPW' %}selected{% endif %}>Kindle Paperwhite 1/2</option>
                                <option value="KPW3" {% if config.kcc_profile == 'KPW3' %}selected{% endif %}>Kindle Paperwhite 3/4</option>
                                <option value="KPW4" {% if config.kcc_profile == 'KPW4' %}selected{% endif %}>Kindle Paperwhite 4</option>
                                <option value="KPW5" {% if config.kcc_profile == 'KPW5' %}selected{% endif %}>Kindle Paperwhite 5</option>
                                <option value="KV" {% if config.kcc_profile == 'KV' %}selected{% endif %}>Kindle Voyage</option>
                                <option value="KO" {% if config.kcc_profile == 'KO' %}selected{% endif %}>Kindle Oasis</option>
                                <option value="KS" {% if config.kcc_profile == 'KS' %}selected{% endif %}>Kindle Scribe</option>
                                <option value="KDX" {% if config.kcc_profile == 'KDX' %}selected{% endif %}>Kindle DX/DXG</option>
                            </optgroup>
                            <optgroup label="Kobo">
                                <option value="KoM" {% if config.kcc_profile == 'KoM' %}selected{% endif %}>Kobo Mini</option>
                                <option value="KoT" {% if config.kcc_profile == 'KoT' %}selected{% endif %}>Kobo Touch</option>
                                <option value="KoG" {% if config.kcc_profile == 'KoG' %}selected{% endif %}>Kobo Glo</option>
                                <option value="KoGHD" {% if config.kcc_profile == 'KoGHD' %}selected{% endif %}>Kobo Glo HD</option>
                                <option value="KoA" {% if config.kcc_profile == 'KoA' %}selected{% endif %}>Kobo Aura</option>
                                <option value="KoAHD" {% if config.kcc_profile == 'KoAHD' %}selected{% endif %}>Kobo Aura HD</option>
                                <option value="KoAH2O" {% if config.kcc_profile == 'KoAH2O' %}selected{% endif %}>Kobo Aura H2O</option>
                                <option value="KoAO" {% if config.kcc_profile == 'KoAO' %}selected{% endif %}>Kobo Aura ONE</option>
                                <option value="KoF" {% if config.kcc_profile == 'KoF' %}selected{% endif %}>Kobo Forma</option>
                                <option value="KoC" {% if config.kcc_profile == 'KoC' %}selected{% endif %}>Kobo Clara HD/2E</option>
                                <option value="KoCE" {% if config.kcc_profile == 'KoCE' %}selected{% endif %}>Kobo Clara Colour</option>
                                <option value="KoL" {% if config.kcc_profile == 'KoL' %}selected{% endif %}>Kobo Libra H2O/2</option>
                                <option value="KoLC" {% if config.kcc_profile == 'KoLC' %}selected{% endif %}>Kobo Libra Colour</option>
                                <option value="KoE" {% if config.kcc_profile == 'KoE' %}selected{% endif %}>Kobo Elipsa</option>
                                <option value="KoE2" {% if config.kcc_profile == 'KoE2' %}selected{% endif %}>Kobo Elipsa 2E</option>
                            </optgroup>
                            <optgroup label="Other">
                                <option value="RM" {% if config.kcc_profile == 'RM' %}selected{% endif %}>reMarkable 1/2</option>
                                <option value="OTHER" {% if config.kcc_profile == 'OTHER' %}selected{% endif %}>Other</option>
                            </optgroup>
                        </select>
                    </div>
                    <div class="group">
                        <label>Output Format</label>
                        <select name="kcc_format">
                            <option value="EPUB" {% if config.kcc_format == 'EPUB' %}selected{% endif %}>EPUB</option>
                            <option value="MOBI" {% if config.kcc_format == 'MOBI' %}selected{% endif %}>MOBI</option>
                            <option value="CBZ" {% if config.kcc_format == 'CBZ' %}selected{% endif %}>CBZ</option>
                            <option value="KFX" {% if config.kcc_format == 'KFX' %}selected{% endif %}>KFX</option>
                        </select>
                    </div>
                    <div class="group">
                        <label>Cropping</label>
                        <select name="kcc_cropping">
                            <option value="0" {% if config.kcc_cropping == '0' %}selected{% endif %}>Disabled</option>
                            <option value="1" {% if config.kcc_cropping == '1' %}selected{% endif %}>Margins</option>
                            <option value="2" {% if config.kcc_cropping == '2' %}selected{% endif %}>Margins + Page Numbers</option>
                        </select>
                    </div>
                    <div class="group">
                        <label>Splitter (Landscape)</label>
                        <select name="kcc_splitter">
                            <option value="0" {% if config.kcc_splitter == '0' %}selected{% endif %}>Disable</option>
                            <option value="1" {% if config.kcc_splitter == '1' %}selected{% endif %}>Rotate</option>
                            <option value="2" {% if config.kcc_splitter == '2' %}selected{% endif %}>Split</option>
                        </select>
                    </div>
                    <div class="group">
                        <label>Gamma (auto or numerical value)</label>
                        <input type="text" name="kcc_gamma" value="{{ config.kcc_gamma }}">
                    </div>
                </div>
                <div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_manga_style" id="manga" {% if config.kcc_manga_style %}checked{% endif %}>
                        <label for="manga">Manga Style (Right-to-Left)</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_hq" id="hq" {% if config.kcc_hq %}checked{% endif %}>
                        <label for="hq">HQ Mode</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_stretch" id="stretch" {% if config.kcc_stretch %}checked{% endif %}>
                        <label for="stretch">Stretch to Screen</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_forcecolor" id="forcecolor" {% if config.kcc_forcecolor %}checked{% endif %}>
                        <label for="forcecolor">Force Color</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_blackborders" id="blackborders" {% if config.kcc_blackborders %}checked{% endif %}>
                        <label for="blackborders">Black Borders</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_colorautocontrast" id="autocontrast" {% if config.kcc_colorautocontrast %}checked{% endif %}>
                        <label for="autocontrast">Color Auto Contrast</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_upscale" id="upscale" {% if config.kcc_upscale %}checked{% endif %}>
                        <label for="upscale">Upscale Images</label>
                    </div>
                    <div class="checkbox-group">
                        <input type="checkbox" name="kcc_metadatatitle" id="metadatatitle" {% if config.kcc_metadatatitle %}checked{% endif %}>
                        <label for="metadatatitle">Metadata Title (Use directory name)</label>
                    </div>
                </div>
            </div>
            
            <input type="submit" value="Save Configuration">
        </form>
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    config = load_config()
    saved = False
    if request.method == 'POST':
        config['kcc_profile'] = request.form.get('kcc_profile', 'KoLC')
        config['kcc_format'] = request.form.get('kcc_format', 'EPUB')
        config['kcc_cropping'] = request.form.get('kcc_cropping', '2')
        config['kcc_splitter'] = request.form.get('kcc_splitter', '2')
        config['kcc_gamma'] = request.form.get('kcc_gamma', 'auto')
        config['kcc_manga_style'] = 'kcc_manga_style' in request.form
        config['kcc_hq'] = 'kcc_hq' in request.form
        config['kcc_stretch'] = 'kcc_stretch' in request.form
        config['kcc_forcecolor'] = 'kcc_forcecolor' in request.form
        config['kcc_blackborders'] = 'kcc_blackborders' in request.form
        config['kcc_colorautocontrast'] = 'kcc_colorautocontrast' in request.form
        config['kcc_upscale'] = 'kcc_upscale' in request.form
        config['kcc_metadatatitle'] = 'kcc_metadatatitle' in request.form
        save_config(config)
        saved = True
    return render_template_string(HTML_TEMPLATE, config=config, saved=saved)

def wait_for_file_ready(filepath):
    last_size = -1
    for _ in range(30):
        try:
            if not os.path.exists(filepath): return False
            current_size = os.path.getsize(filepath)
            if current_size > 0 and current_size == last_size:
                return True
            last_size = current_size
        except OSError: pass
        time.sleep(2)
    return False

def get_newest_file(directory):
    files = [os.path.join(directory, f) for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    return max(files, key=os.path.getmtime) if files else None

def handle_output_renaming(produced_file, target_dir, original_input):
    if not produced_file: return False
    filename = os.path.basename(produced_file)
    if filename.endswith('.kepub.epub'): filename = filename[:-11] + '.kepub'
    elif filename.endswith('.epub'): filename = filename[:-5] + '.kepub'
    final_path = os.path.join(target_dir, filename)
    os.makedirs(target_dir, exist_ok=True)
    shutil.move(produced_file, final_path)
    if os.path.exists(original_input): os.remove(original_input)
    return True

def process_file(filepath, c_type):
    if filepath in PROCESSING_LOCKS: return
    PROCESSING_LOCKS.add(filepath)
    try:
        if not wait_for_file_ready(filepath): return
        config = load_config()
        rel_dir = os.path.dirname(os.path.relpath(filepath, BOOKS_IN if c_type == 'book' else COMICS_IN))
        if rel_dir == '.': rel_dir = ''
        out_base = BOOKS_OUT if c_type == 'book' else COMICS_OUT
        target_dir = os.path.join(out_base, rel_dir)
        temp_out = os.path.join('/tmp', os.path.basename(filepath) + '_out')
        os.makedirs(temp_out, exist_ok=True)
        
        if c_type == 'book':
            print(f"Running Kepubify on {filepath}", flush=True)
            cmd = ['kepubify', '--calibre', '--inplace', '--output', temp_out, filepath]
            result = subprocess.run(cmd, capture_output=True, text=True)
        else:
            print(f"Running KCC on {filepath}", flush=True)
            cmd = ['kcc-c2e', '-p', config['kcc_profile'], '-f', config['kcc_format'], 
                   '--splitter', config['kcc_splitter'], '--cropping', config['kcc_cropping'], '-o', temp_out]
            if config['kcc_manga_style']: cmd.append('-m')
            if config['kcc_hq']: cmd.append('-q')
            if config['kcc_stretch']: cmd.append('-s')
            if config['kcc_forcecolor']: cmd.append('--forcecolor')
            if config['kcc_blackborders']: cmd.append('-b')
            if config['kcc_colorautocontrast']: cmd.append('-c')
            if config['kcc_upscale']: cmd.append('-u')
            if config['kcc_metadatatitle']: cmd.append('-t')
            if config['kcc_gamma'] and config['kcc_gamma'].lower() != 'auto':
                cmd.extend(['-g', config['kcc_gamma']])
            cmd.append(filepath)
            result = subprocess.run(cmd, capture_output=True, text=True)
            
        if result.returncode == 0:
            produced = get_newest_file(temp_out)
            if handle_output_renaming(produced, target_dir, filepath):
                print(f"Successfully processed {filepath}", flush=True)
        else:
            print(f"Failed to process {filepath}\\nError: {result.stderr}", flush=True)
            if os.path.exists(filepath): os.rename(filepath, filepath + '.failed')
        if os.path.exists(temp_out): shutil.rmtree(temp_out)
    except Exception as e: print(f"Exception processing {filepath}: {e}", flush=True)
    finally: PROCESSING_LOCKS.remove(filepath)

def scan_directories():
    for root, _, files in os.walk(BOOKS_IN):
        for f in files:
            if (f.lower().endswith('.epub') or f.lower().endswith('.kepub')) and not f.lower().endswith('.failed'):
                threading.Thread(target=process_file, args=(os.path.join(root, f), 'book')).start()
    for root, _, files in os.walk(COMICS_IN):
        for f in files:
            if (f.lower().endswith('.cbz') or f.lower().endswith('.cbr') or f.lower().endswith('.zip') or f.lower().endswith('.rar')) and not f.lower().endswith('.failed'):
                threading.Thread(target=process_file, args=(os.path.join(root, f), 'comic')).start()

def watch_loop():
    while True:
        scan_directories()
        time.sleep(10)

if __name__ == '__main__':
    threading.Thread(target=watch_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)
