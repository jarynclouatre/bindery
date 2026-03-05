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
