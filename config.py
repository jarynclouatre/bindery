"""Persistent settings management — load, save, and default KCC/kepubify configuration."""

import os
import json
import threading
from typing import Any

CONFIG_DIR  = '/app/config'
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.json')

ConfigDict = dict[str, Any]

DEFAULT_CONFIG: ConfigDict = {
    'kcc_profile':           'KoLC',
    'kcc_manga_style':       False,
    'kcc_hq':                False,
    'kcc_two_panel':         False,
    'kcc_webtoon':           False,
    'kcc_borders':           'black',
    'kcc_forcecolor':        True,
    'kcc_colorautocontrast': True,
    'kcc_colorcurve':        False,
    'kcc_eraserainbow':      False,
    'kcc_mozjpeg':           False,
    'kcc_stretch':           True,
    'kcc_upscale':           False,
    'kcc_nosplitrotate':     False,
    'kcc_rotate':            False,
    'kcc_cropping':          '2',
    'kcc_croppingpower':     '1.0',
    'kcc_croppingminimum':   '0',
    'kcc_splitter':          '1',
    'kcc_gamma':             '0',
    'kcc_format':            'EPUB',
    'kcc_nokepub':           False,
    'kcc_metadatatitle':     True,
    'kcc_author':            '',
    'kcc_batchsplit':        '0',
    'kcc_customwidth':       '',
    'kcc_customheight':      '',
    'file_wait_timeout':     60,
    'watcher_mode':          'poll',
    'apprise_urls':          '',
    'notify_on_success':     True,
    'notify_on_failure':     True,
    'originals':             'delete',
    'bundle_chapter_folders': False,
    'profiles':              {},
}

# Keys a device profile overrides. Everything else — watcher, notifications,
# folder handling — is shared across profiles.
KCC_KEYS = frozenset(k for k in DEFAULT_CONFIG if k.startswith('kcc_'))

_config_lock = threading.Lock()


def load_config() -> ConfigDict:
    """Load settings from disk, filling any missing keys from DEFAULT_CONFIG.

    Returns a copy of DEFAULT_CONFIG if the file is absent or unreadable.
    """
    with _config_lock:
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    config: ConfigDict = json.load(f)
                # Older configs stored a preserve_originals bool; map it onto originals.
                if 'preserve_originals' in config:
                    config.setdefault(
                        'originals',
                        'archive' if config['preserve_originals'] else 'delete')
                    del config['preserve_originals']
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
                return config
            except Exception:
                pass
        return dict(DEFAULT_CONFIG)


def profile_overrides(config: ConfigDict, name: str) -> ConfigDict:
    """Return config with the named profile's KCC settings laid over the top.

    Unknown names return config unchanged. Keys a profile has never saved
    inherit the main settings, so new toggles work everywhere immediately.
    """
    profiles = config.get('profiles') or {}
    overrides = profiles.get(name)
    if not isinstance(overrides, dict):
        return config
    merged = dict(config)
    merged.update({k: v for k, v in overrides.items() if k in KCC_KEYS})
    return merged


def save_config(config: ConfigDict) -> None:
    """Write config to disk atomically via a temp file and os.replace."""
    with _config_lock:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        tmp = CONFIG_FILE + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(config, f, indent=4)
        os.replace(tmp, CONFIG_FILE)
