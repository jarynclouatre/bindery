import json
import time
from unittest.mock import patch

import pytest

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


def test_api_stats_returns_fields(client):
    resp = client.get('/api/stats')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    for key in ('converted', 'bytes_saved', 'bytes_saved_human',
                'queued', 'processing', 'failed', 'last_conversion'):
        assert key in data
    assert isinstance(data['converted'], int)


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


@pytest.mark.parametrize('field, bad, expected', [
    ('kcc_format',        'MOBI',            'EPUB'),   # MOBI/KFX dropped in v3.4.0
    ('file_wait_timeout', '9999',            300),      # numeric clamp to the max
    ('watcher_mode',      'hacked',          'poll'),
    ('originals',         'wipe-everything', 'delete'),
])
def test_validate_post_clamps_bad_field(client, tmp_path, field, bad, expected):
    saved, _ = _post(client, tmp_path, **{field: bad})
    assert saved[field] == expected


def test_index_get_shows_originals_control(client):
    resp = client.get('/')
    assert b'name="originals"' in resp.data
    for value in (b'value="delete"', b'value="archive"', b'value="keep"'):
        assert value in resp.data


def test_post_originals_keep_saves(client, tmp_path):
    saved, _ = _post(client, tmp_path, originals='keep')
    assert saved['originals'] == 'keep'


def test_post_defaults_originals_to_delete(client, tmp_path):
    # A form that omits the field (older cached page) must not silently enable
    # keep/archive.
    saved, _ = _post(client, tmp_path)
    assert saved['originals'] == 'delete'


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
    # The endpoint fires os.kill from a thread ~0.5s after responding; the
    # patch must stay up until that happens or the real kill hits pytest.
    with patch('app.os.kill') as mock_kill:
        resp = client.post('/api/restart')
        assert resp.status_code == 200
        assert json.loads(resp.data) == {'status': 'restarting'}
        deadline = time.time() + 5
        while not mock_kill.called and time.time() < deadline:
            time.sleep(0.05)
    assert mock_kill.called


def test_api_profiles_create_collision_and_delete(client, tmp_path):
    config_file = tmp_path / 'settings.json'
    comics_in   = tmp_path / 'comics_in'
    comics_out  = tmp_path / 'comics_out'
    comics_in.mkdir()
    comics_out.mkdir()

    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(tmp_path)), \
         patch('app.COMICS_IN', str(comics_in)), \
         patch('app.COMICS_OUT', str(comics_out)):
        resp = client.post('/api/profiles', json={'action': 'create', 'name': 'kobo'})
        assert resp.status_code == 200
        saved = json.loads(config_file.read_text())
        assert 'kobo' in saved['profiles']
        assert saved['profiles']['kobo']['kcc_profile'] == saved['kcc_profile']
        assert (comics_in / 'kobo').is_dir()
        assert (comics_out / 'kobo').is_dir()

        (comics_in / 'kindle').mkdir()
        (comics_in / 'kindle' / 'x.cbz').write_bytes(b'x')
        resp = client.post('/api/profiles', json={'action': 'create', 'name': 'kindle'})
        assert resp.status_code == 409

        resp = client.post('/api/profiles', json={'action': 'create', 'name': '.archive'})
        assert resp.status_code == 400
        resp = client.post('/api/profiles', json={'action': 'create', 'name': 'kobo'})
        assert resp.status_code == 409

        resp = client.post('/api/profiles', json={'action': 'delete', 'name': 'kobo'})
        assert resp.status_code == 200
        saved = json.loads(config_file.read_text())
        assert saved['profiles'] == {}
        assert (comics_in / 'kobo').is_dir()


def test_index_post_editing_profile_saves_kcc_to_profile_only(client, tmp_path):
    config_file = tmp_path / 'settings.json'
    base = dict(cfg.DEFAULT_CONFIG)
    base['profiles'] = {'kobo': {}}
    config_file.write_text(json.dumps(base))

    saved, _ = _post(client, tmp_path, editing_profile='kobo', kcc_profile='KPW5')
    assert saved['profiles']['kobo']['kcc_profile'] == 'KPW5'
    assert saved['kcc_profile'] == cfg.DEFAULT_CONFIG['kcc_profile']


def test_index_post_editing_missing_profile_keeps_main_kcc(client, tmp_path):
    """A save against a profile deleted in another tab must not write the
    stale profile values over the main KCC settings."""
    config_file = tmp_path / 'settings.json'
    config_file.write_text(json.dumps(dict(cfg.DEFAULT_CONFIG)))

    saved, _ = _post(client, tmp_path, editing_profile='ghost',
                     kcc_profile='KPW5', file_wait_timeout='90')
    assert saved['kcc_profile'] == cfg.DEFAULT_CONFIG['kcc_profile']
    assert 'ghost' not in saved['profiles']
    assert saved['file_wait_timeout'] == 90


def _upload(client, tmp_path, filename, content=b'data', profile=None):
    from io import BytesIO
    config_file = tmp_path / 'settings.json'
    books_in  = tmp_path / 'books_in'
    comics_in = tmp_path / 'comics_in'
    books_in.mkdir(exist_ok=True)
    comics_in.mkdir(exist_ok=True)
    data = {'files': (BytesIO(content), filename)}
    if profile is not None:
        data['profile'] = profile
    with patch.object(cfg, 'CONFIG_FILE', str(config_file)), \
         patch.object(cfg, 'CONFIG_DIR', str(tmp_path)), \
         patch('app.BOOKS_IN', str(books_in)), \
         patch('app.COMICS_IN', str(comics_in)):
        resp = client.post('/api/upload', data=data,
                           content_type='multipart/form-data')
    return resp, books_in, comics_in


def test_api_upload_routes_by_extension(client, tmp_path):
    resp, books_in, comics_in = _upload(client, tmp_path, 'novel.epub')
    assert resp.status_code == 200
    assert (books_in / 'novel.epub').read_bytes() == b'data'

    resp, books_in, comics_in = _upload(client, tmp_path, 'issue.cbz')
    assert (comics_in / 'issue.cbz').exists()
    assert not (comics_in / '.uploading' / 'issue.cbz').exists()


def test_api_upload_rejects_unsupported_and_dodges_collisions(client, tmp_path):
    resp, _books, comics_in = _upload(client, tmp_path, 'virus.exe')
    assert json.loads(resp.data)['files'][0]['error'] == 'unsupported file type'

    (comics_in / 'issue.cbz').write_bytes(b'old')
    resp, _books, comics_in = _upload(client, tmp_path, 'issue.cbz')
    saved_as = json.loads(resp.data)['files'][0]['name']
    assert saved_as != 'issue.cbz'
    assert (comics_in / saved_as).read_bytes() == b'data'
    assert (comics_in / 'issue.cbz').read_bytes() == b'old'


def test_api_upload_lands_in_profile_folder(client, tmp_path):
    config_file = tmp_path / 'settings.json'
    base = dict(cfg.DEFAULT_CONFIG)
    base['profiles'] = {'kobo': {}}
    config_file.write_text(json.dumps(base))
    resp, _books, comics_in = _upload(client, tmp_path, 'issue.cbz', profile='kobo')
    assert (comics_in / 'kobo' / 'issue.cbz').exists()

    resp, _books, comics_in = _upload(client, tmp_path, 'other.cbz', profile='ghost')
    assert (comics_in / 'other.cbz').exists()
