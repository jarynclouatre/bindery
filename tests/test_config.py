import json
import pytest
from unittest.mock import patch

import config as cfg


def test_load_config_returns_defaults_when_no_file(tmp_path):
    missing = str(tmp_path / 'settings.json')
    with patch.object(cfg, 'CONFIG_FILE', missing):
        result = cfg.load_config()
    assert result == cfg.DEFAULT_CONFIG


def test_load_config_fills_missing_keys(tmp_path):
    # Write a config that only has one key
    partial = {'kcc_profile': 'KPW5'}
    config_file = tmp_path / 'settings.json'
    config_file.write_text(json.dumps(partial))
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)):
        result = cfg.load_config()
    # The saved key should be preserved
    assert result['kcc_profile'] == 'KPW5'
    # All default keys should be present
    for key in cfg.DEFAULT_CONFIG:
        assert key in result


def test_load_config_returns_defaults_on_bad_json(tmp_path):
    config_file = tmp_path / 'settings.json'
    config_file.write_text('this is not valid json {{{')
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)):
        result = cfg.load_config()
    assert result == cfg.DEFAULT_CONFIG


def test_save_load_roundtrip(tmp_path):
    config_file = tmp_path / 'settings.json'
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        cfg.save_config(cfg.DEFAULT_CONFIG)
        result = cfg.load_config()
    assert result == cfg.DEFAULT_CONFIG


def test_save_config_creates_directory(tmp_path):
    nested_dir  = tmp_path / 'deep' / 'nested'
    config_file = nested_dir / 'settings.json'
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(nested_dir)):
        cfg.save_config(cfg.DEFAULT_CONFIG)
    assert config_file.exists()


def test_save_config_atomic_no_partial_file_on_error(tmp_path):
    # If writing fails mid-way, the original settings.json must not be
    # corrupted. We simulate this by making open() raise after the save
    # starts, then confirm the original file is intact.
    config_file = tmp_path / 'settings.json'
    original = {'kcc_profile': 'KoLC'}
    config_file.write_text(json.dumps(original))

    real_open = open
    call_count = [0]

    def patched_open(path, mode='r', **kwargs):
        if 'w' in mode and str(config_file.parent) in str(path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("Simulated disk full")
        return real_open(path, mode, **kwargs)

    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(tmp_path)), \
         patch('builtins.open', patched_open):
        try:
            cfg.save_config(cfg.DEFAULT_CONFIG)
        except OSError:
            pass

    # Original file must still be valid and untouched
    saved = json.loads(config_file.read_text())
    assert saved == original


def test_profile_overrides_merges_kcc_keys_only():
    config = dict(cfg.DEFAULT_CONFIG)
    config['profiles'] = {'kobo': {'kcc_profile': 'KPW5', 'preserve_originals': True}}
    merged = cfg.profile_overrides(config, 'kobo')
    assert merged['kcc_profile'] == 'KPW5'
    assert merged['preserve_originals'] is False
    assert cfg.profile_overrides(config, 'nope') is config


def test_profile_overrides_inherits_unsaved_keys():
    """A profile saved before a new toggle existed must inherit the main
    setting for it, not crash or zero it."""
    config = dict(cfg.DEFAULT_CONFIG)
    config['kcc_mozjpeg'] = True
    config['profiles'] = {'old': {'kcc_profile': 'KPW5'}}
    merged = cfg.profile_overrides(config, 'old')
    assert merged['kcc_mozjpeg'] is True
