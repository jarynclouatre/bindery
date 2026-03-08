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


def test_api_logs_returns_json(client):
    resp = client.get('/api/logs')
    assert resp.status_code == 200
    data = __import__('json').loads(resp.data)
    assert 'logs' in data
    assert isinstance(data['logs'], list)


def test_validate_post_clamps_borders_invalid(client, tmp_path):
    import config as cfg
    config_file = tmp_path / 'settings.json'
    with __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        resp = client.post('/', data={
            'kcc_profile':         'KPW5',
            'kcc_format':          'EPUB',
            'kcc_cropping':        '2',
            'kcc_croppingpower':   '1.0',
            'kcc_croppingminimum': '1',
            'kcc_splitter':        '1',
            'kcc_gamma':           'injected',
            'kcc_batchsplit':      '0',
            'kcc_borders':         'purple',
            'kcc_author':          '',
            'kcc_customwidth':     '',
            'kcc_customheight':    '',
        })
        assert resp.status_code == 200
        saved = __import__('json').loads(config_file.read_text())
    assert saved['kcc_borders'] == 'black'
    assert saved['kcc_gamma'] == '0'


def test_validate_post_clamps_profile_invalid(client, tmp_path):
    import config as cfg
    config_file = tmp_path / 'settings.json'
    with __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        client.post('/', data={
            'kcc_profile':         'HACKED',
            'kcc_format':          'DOCX',
            'kcc_cropping':        '9',
            'kcc_croppingpower':   '1.0',
            'kcc_croppingminimum': '1',
            'kcc_splitter':        '9',
            'kcc_gamma':           '0',
            'kcc_batchsplit':      '9',
            'kcc_borders':         'black',
            'kcc_author':          '',
            'kcc_customwidth':     '',
            'kcc_customheight':    '',
        })
        saved = __import__('json').loads(config_file.read_text())
    assert saved['kcc_profile']    == 'KoLC'
    assert saved['kcc_format']     == 'EPUB'
    assert saved['kcc_cropping']   == '2'
    assert saved['kcc_splitter']   == '1'
    assert saved['kcc_batchsplit'] == '0'


def test_validate_post_file_wait_timeout_clamped(client, tmp_path):
    import config as cfg
    config_file = tmp_path / 'settings.json'
    with __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        client.post('/', data={
            'kcc_profile': 'KPW5', 'kcc_format': 'EPUB', 'kcc_cropping': '2',
            'kcc_croppingpower': '1.0', 'kcc_croppingminimum': '1',
            'kcc_splitter': '1', 'kcc_gamma': '0', 'kcc_batchsplit': '0',
            'kcc_borders': 'black', 'kcc_author': '', 'kcc_customwidth': '',
            'kcc_customheight': '', 'file_wait_timeout': '9999',
        })
        saved = __import__('json').loads(config_file.read_text())
    assert saved['file_wait_timeout'] == 300


def test_validate_post_watcher_mode_invalid(client, tmp_path):
    import config as cfg
    config_file = tmp_path / 'settings.json'
    with __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         __import__('unittest.mock', fromlist=['patch']).patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        client.post('/', data={
            'kcc_profile': 'KPW5', 'kcc_format': 'EPUB', 'kcc_cropping': '2',
            'kcc_croppingpower': '1.0', 'kcc_croppingminimum': '1',
            'kcc_splitter': '1', 'kcc_gamma': '0', 'kcc_batchsplit': '0',
            'kcc_borders': 'black', 'kcc_author': '', 'kcc_customwidth': '',
            'kcc_customheight': '', 'watcher_mode': 'hacked',
        })
        saved = __import__('json').loads(config_file.read_text())
    assert saved['watcher_mode'] == 'poll'


def test_api_restart_returns_json(client):
    from unittest.mock import patch
    with patch('app.os.kill') as mock_kill:
        resp = client.post('/api/restart')
    assert resp.status_code == 200
    assert __import__('json').loads(resp.data) == {'status': 'restarting'}
