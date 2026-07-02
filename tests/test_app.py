import json
from unittest.mock import patch

import config as cfg

_BASE_FORM = {
    'kcc_profile': 'KPW5', 'kcc_format': 'EPUB', 'kcc_cropping': '2',
    'kcc_croppingpower': '1.0', 'kcc_croppingminimum': '1',
    'kcc_splitter': '1', 'kcc_gamma': '0', 'kcc_batchsplit': '0',
    'kcc_borders': 'black', 'kcc_author': '', 'kcc_customwidth': '',
    'kcc_customheight': '',
}


def _post(client, tmp_path, **overrides):
    """POST the settings form against a temp config file, return what was saved."""
    config_file = tmp_path / 'settings.json'
    data = {**_BASE_FORM, **overrides}
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(tmp_path)):
        resp = client.post('/', data=data)
    assert resp.status_code == 200
    return json.loads(config_file.read_text()), resp


def test_health(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert json.loads(resp.data) == {'status': 'ok'}


def test_index_get_returns_200(client):
    resp = client.get('/')
    assert resp.status_code == 200
    assert b'Bindery' in resp.data


def test_index_post_saves_and_confirms(client, tmp_path):
    saved, resp = _post(client, tmp_path)
    assert b'Settings saved' in resp.data
    assert saved['kcc_profile'] == 'KPW5'


def test_validate_post_clamps_invalid_choices(client, tmp_path):
    saved, _ = _post(client, tmp_path,
                     kcc_profile='HACKED', kcc_format='DOCX', kcc_cropping='9',
                     kcc_splitter='9', kcc_batchsplit='9',
                     kcc_gamma='injected', kcc_borders='purple')
    assert saved['kcc_profile']    == 'KoLC'
    assert saved['kcc_format']     == 'EPUB'
    assert saved['kcc_cropping']   == '2'
    assert saved['kcc_splitter']   == '1'
    assert saved['kcc_batchsplit'] == '0'
    assert saved['kcc_gamma']      == '0'
    assert saved['kcc_borders']    == 'black'


def test_validate_post_rejects_removed_formats(client, tmp_path):
    # MOBI/KFX were dropped in v3.4.0 — they can't convert in this image.
    saved, _ = _post(client, tmp_path, kcc_format='MOBI')
    assert saved['kcc_format'] == 'EPUB'


def test_validate_post_file_wait_timeout_clamped(client, tmp_path):
    saved, _ = _post(client, tmp_path, file_wait_timeout='9999')
    assert saved['file_wait_timeout'] == 300


def test_validate_post_watcher_mode_invalid(client, tmp_path):
    saved, _ = _post(client, tmp_path, watcher_mode='hacked')
    assert saved['watcher_mode'] == 'poll'


def test_validate_post_saves_apprise_url(client, tmp_path):
    saved, _ = _post(client, tmp_path,
                     apprise_urls='ntfy://server/bindery',
                     notify_on_success='on', notify_on_failure='on')
    assert saved['apprise_urls']      == 'ntfy://server/bindery'
    assert saved['notify_on_success'] is True
    assert saved['notify_on_failure'] is True


def test_validate_post_notify_unchecked_saves_false(client, tmp_path):
    saved, _ = _post(client, tmp_path)
    assert saved['notify_on_success'] is False
    assert saved['notify_on_failure'] is False


def test_api_restart_returns_json(client):
    with patch('app.os.kill'):
        resp = client.post('/api/restart')
    assert resp.status_code == 200
    assert json.loads(resp.data) == {'status': 'restarting'}
