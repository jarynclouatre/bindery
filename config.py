import os
import json

CONFIG_DIR  = '/app/config'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')

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
