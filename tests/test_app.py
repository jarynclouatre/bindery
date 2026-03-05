import json
from unittest.mock import patch

import config as cfg


def test_health(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert json.loads(resp.data) == {'status': 'ok'}


def test_index_get_returns_200(client):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Bindery' in resp.data


def test_index_get_shows_version(client):
    import app
    resp = client.get('/')
    assert app.VERSION.encode() in resp.data


def test_index_post_saves_and_confirms(client, tmp_path):
    config_file = tmp_path / 'settings.json'
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        resp = client.post('/', data={
            'kcc_profile':        'KPW5',
            'kcc_format':         'EPUB',
            'kcc_cropping':       '1',
            'kcc_croppingpower':  '1.0',
            'kcc_croppingminimum': '1',
            'kcc_splitter':       '1',
            'kcc_gamma':          '0',
            'kcc_batchsplit':     '0',
            'kcc_author':         '',
            'kcc_customwidth':    '',
            'kcc_customheight':   '',
        })
    assert resp.status_code == 200
    assert b'Settings saved' in resp.data


def test_index_post_persists_profile(client, tmp_path):
    config_file = tmp_path / 'settings.json'
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        client.post('/', data={
            'kcc_profile':        'KoF',
            'kcc_format':         'EPUB',
            'kcc_cropping':       '2',
            'kcc_croppingpower':  '1.0',
            'kcc_croppingminimum': '1',
            'kcc_splitter':       '1',
            'kcc_gamma':          '0',
            'kcc_batchsplit':     '0',
            'kcc_author':         '',
            'kcc_customwidth':    '',
            'kcc_customheight':   '',
        })
        saved = json.loads(config_file.read_text())
    assert saved['kcc_profile'] == 'KoF'
