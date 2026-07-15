"""Tests for job registry, retry, status API, and file browser API."""

import json
from unittest.mock import patch, MagicMock

import processor
import app as bindery_app
from config import DEFAULT_CONFIG

# ── Job registry ──────────────────────────────────────────────────────────────

def test_register_job_creates_queued_entry(tmp_path):
    jobs_file = tmp_path / 'jobs.json'
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        job_id = processor._register_job('/Comics_in/test.cbz', 'comic')
    job = processor.JOB_REGISTRY[job_id]
    assert job['state']    == 'queued'
    assert job['filename'] == 'test.cbz'
    assert job['type']     == 'comic'
    assert job['created']  is not None
    assert job['started']  is None
    assert job['finished'] is None
    assert job['error']    is None

def test_register_job_persists_to_disk(tmp_path):
    jobs_file = tmp_path / 'jobs.json'
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        processor._register_job('/Comics_in/test.cbz', 'comic')
    assert jobs_file.exists()
    data = json.loads(jobs_file.read_text())
    assert len(data) == 1

def test_update_job_changes_state_and_persists(tmp_path):
    jobs_file = tmp_path / 'jobs.json'
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        job_id = processor._register_job('/Comics_in/test.cbz', 'comic')
        processor._update_job(job_id, state='processing', started='2024-01-01T00:00:00Z')
    job = processor.JOB_REGISTRY[job_id]
    assert job['state']   == 'processing'
    assert job['started'] == '2024-01-01T00:00:00Z'
    data = json.loads(jobs_file.read_text())
    assert data[job_id]['state'] == 'processing'

def test_load_job_registry_populates_from_disk(tmp_path):
    jobs_file = tmp_path / 'jobs.json'
    data = {'abc123': {'id': 'abc123', 'filename': 'test.cbz', 'state': 'success',
                       'created': '2024-01-01T00:00:00Z'}}
    jobs_file.write_text(json.dumps(data))
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        processor._load_job_registry()
    assert 'abc123' in processor.JOB_REGISTRY

def test_load_job_registry_does_not_replace_dict_reference(tmp_path):
    """_load_job_registry must use .update() so the reference in app.py stays valid."""
    original_ref = processor.JOB_REGISTRY
    jobs_file = tmp_path / 'jobs.json'
    data = {'x': {'id': 'x', 'state': 'success', 'created': '2024-01-01T00:00:00Z'}}
    jobs_file.write_text(json.dumps(data))
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        processor._load_job_registry()
    assert processor.JOB_REGISTRY is original_ref, \
        "_load_job_registry replaced the dict object — app.py's import reference is now stale"

def test_load_job_registry_drops_stale_running_jobs(tmp_path):
    """Jobs persisted as queued/processing died with the old process — they
    must not come back as permanent 'processing' rows in the UI."""
    jobs_file = tmp_path / 'jobs.json'
    data = {
        'done':  {'id': 'done',  'state': 'success',    'created': '2024-01-01T00:00:00Z'},
        'dead':  {'id': 'dead',  'state': 'processing', 'created': '2024-01-01T00:00:01Z'},
        'ghost': {'id': 'ghost', 'state': 'queued',     'created': '2024-01-01T00:00:02Z'},
    }
    jobs_file.write_text(json.dumps(data))
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        processor._load_job_registry()
    assert set(processor.JOB_REGISTRY) == {'done'}

def test_load_job_registry_ignores_bad_json(tmp_path):
    jobs_file = tmp_path / 'jobs.json'
    jobs_file.write_text('not json {{{')
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        processor._load_job_registry()
    assert processor.JOB_REGISTRY == {}

def test_register_job_prunes_oldest_completed_when_over_max(tmp_path):
    jobs_file = tmp_path / 'jobs.json'
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)), \
         patch.object(processor, 'MAX_JOBS', 3):
        ids = [processor._register_job(f'/in/f{i}.cbz', 'comic') for i in range(3)]
        processor._update_job(ids[0], state='success',
                               started='2024-01-01T00:00:00Z', finished='2024-01-01T00:01:00Z')
        processor._update_job(ids[1], state='failed',
                               started='2024-01-01T00:00:00Z', finished='2024-01-01T00:01:00Z')
        processor._register_job('/in/f3.cbz', 'comic')
    assert len(processor.JOB_REGISTRY) == 3
    assert ids[0] not in processor.JOB_REGISTRY
    assert ids[2] in processor.JOB_REGISTRY

# ── retry_file ────────────────────────────────────────────────────────────────

def test_retry_file_renames_and_requeues(tmp_path):
    src    = tmp_path / 'test.cbz'
    failed = tmp_path / 'test.cbz.failed'
    failed.write_bytes(b'data')
    jobs_file = tmp_path / 'jobs.json'

    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        job_id = processor._register_job(str(src), 'comic')
        processor._update_job(job_id, state='failed')

    with patch.object(processor, 'JOBS_FILE', str(jobs_file)), \
         patch('threading.Thread') as mock_thread:
        mock_thread.return_value = MagicMock()
        result = processor.retry_file(job_id)

    assert result is True
    assert src.exists()
    assert not failed.exists()
    assert processor.JOB_REGISTRY[job_id]['state'] == 'queued'
    assert processor.JOB_REGISTRY[job_id]['error'] is None

def test_retry_file_returns_false_for_bad_states(tmp_path):
    """No-op for a job that never failed, a failed job whose .failed file has
    vanished, and an unknown id."""
    jobs_file = tmp_path / 'jobs.json'
    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        not_failed = processor._register_job('/in/test.cbz', 'comic')
        gone = processor._register_job('/in/ghost.cbz', 'comic')
        processor._update_job(gone, state='failed')
        assert processor.retry_file(not_failed) is False
        assert processor.retry_file(gone) is False
        assert processor.retry_file('doesnotexist') is False

def test_retry_file_refuses_to_overwrite_replacement_file(tmp_path):
    """If a new file was dropped under the original name, retry must not clobber it."""
    src    = tmp_path / 'test.cbz'
    failed = tmp_path / 'test.cbz.failed'
    src.write_bytes(b'newly dropped file')
    failed.write_bytes(b'old failed data')
    jobs_file = tmp_path / 'jobs.json'

    with patch.object(processor, 'JOBS_FILE', str(jobs_file)):
        job_id = processor._register_job(str(src), 'comic')
        processor._update_job(job_id, state='failed')
        assert processor.retry_file(job_id) is False

    assert src.read_bytes() == b'newly dropped file'
    assert failed.exists()

# ── process_file registry integration ─────────────────────────────────────────

def test_process_file_sets_failed_state_on_conversion_error(tmp_path):
    comics_in = tmp_path / 'comics_in'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake')
    jobs_file = tmp_path / 'jobs.json'

    with patch.object(processor, 'COMICS_IN',  str(comics_in)), \
         patch.object(processor, 'COMICS_OUT', str(tmp_path / 'out')), \
         patch.object(processor, 'JOBS_FILE',  str(jobs_file)), \
         patch('processor.load_config', return_value=dict(DEFAULT_CONFIG)), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion', side_effect=processor.ConversionError(1)):
        processor.process_file(str(src), 'comic')

    assert len(processor.JOB_REGISTRY) == 1
    job = list(processor.JOB_REGISTRY.values())[0]
    assert job['state']    == 'failed'
    assert job['finished'] is not None
    assert 'exit 1' in job['error']

def test_process_file_sets_success_state(tmp_path):
    comics_in  = tmp_path / 'comics_in'
    comics_out = tmp_path / 'comics_out'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake')
    fake_out = tmp_path / 'fake.epub'
    fake_out.write_bytes(b'epub')
    jobs_file = tmp_path / 'jobs.json'

    with patch.object(processor, 'COMICS_IN',  str(comics_in)), \
         patch.object(processor, 'COMICS_OUT', str(comics_out)), \
         patch.object(processor, 'JOBS_FILE',  str(jobs_file)), \
         patch('processor.load_config', return_value=dict(DEFAULT_CONFIG)), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion', return_value=None), \
         patch('processor.get_output_files', return_value=[str(fake_out)]), \
         patch('processor.move_output_file', return_value=None):
        processor.process_file(str(src), 'comic')

    job = list(processor.JOB_REGISTRY.values())[0]
    assert job['state'] == 'success'

def test_process_file_removes_job_on_skip(tmp_path):
    comics_in = tmp_path / 'comics_in'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake')
    jobs_file = tmp_path / 'jobs.json'

    with patch.object(processor, 'COMICS_IN',  str(comics_in)), \
         patch.object(processor, 'COMICS_OUT', str(tmp_path / 'out')), \
         patch.object(processor, 'JOBS_FILE',  str(jobs_file)), \
         patch('processor.load_config', return_value=dict(DEFAULT_CONFIG)), \
         patch('processor.wait_for_file_ready', return_value=False):
        processor.process_file(str(src), 'comic')

    assert len(processor.JOB_REGISTRY) == 0

# ── /api/status ───────────────────────────────────────────────────────────────

def test_api_status_empty(client):
    resp = client.get('/api/status')
    assert resp.status_code == 200
    assert json.loads(resp.data) == {'jobs': []}

def test_api_status_returns_jobs(client):
    processor.JOB_REGISTRY['abc'] = {
        'id': 'abc', 'filename': 'test.cbz', 'filepath': '/in/test.cbz',
        'type': 'comic', 'state': 'success',
        'created': '2024-01-01T00:00:00Z', 'started': '2024-01-01T00:00:01Z',
        'finished': '2024-01-01T00:01:00Z', 'error': None,
    }
    resp = client.get('/api/status')
    data = json.loads(resp.data)
    assert len(data['jobs']) == 1
    assert data['jobs'][0]['filename'] == 'test.cbz'

def test_api_status_sorts_newest_first(client):
    processor.JOB_REGISTRY['old'] = {
        'id': 'old', 'filename': 'old.cbz', 'filepath': '/in/old.cbz',
        'type': 'comic', 'state': 'success',
        'created': '2024-01-01T00:00:00Z', 'started': None,
        'finished': None, 'error': None,
    }
    processor.JOB_REGISTRY['new'] = {
        'id': 'new', 'filename': 'new.cbz', 'filepath': '/in/new.cbz',
        'type': 'comic', 'state': 'queued',
        'created': '2024-01-02T00:00:00Z', 'started': None,
        'finished': None, 'error': None,
    }
    data = json.loads(client.get('/api/status').data)
    assert data['jobs'][0]['id'] == 'new'
    assert data['jobs'][1]['id'] == 'old'

# ── /api/retry ────────────────────────────────────────────────────────────────

def test_api_retry_missing_job_id(client):
    resp = client.post('/api/retry',
                       data=json.dumps({}),
                       content_type='application/json')
    assert resp.status_code == 400

def test_api_retry_unknown_job_returns_not_ok(client):
    resp = client.post('/api/retry',
                       data=json.dumps({'job_id': 'doesnotexist'}),
                       content_type='application/json')
    assert resp.status_code == 200
    assert json.loads(resp.data)['ok'] is False

def test_api_retry_success(client, tmp_path):
    src    = tmp_path / 'test.cbz'
    failed = tmp_path / 'test.cbz.failed'
    failed.write_bytes(b'data')
    jobs_file = tmp_path / 'jobs.json'

    processor.JOB_REGISTRY['job1'] = {
        'id': 'job1', 'filename': 'test.cbz', 'filepath': str(src),
        'type': 'comic', 'state': 'failed',
        'created': '2024-01-01T00:00:00Z', 'started': '2024-01-01T00:00:01Z',
        'finished': '2024-01-01T00:01:00Z', 'error': 'exit 1',
    }

    with patch.object(processor, 'JOBS_FILE', str(jobs_file)), \
         patch('threading.Thread') as mock_thread:
        mock_thread.return_value = MagicMock()
        resp = client.post('/api/retry',
                           data=json.dumps({'job_id': 'job1'}),
                           content_type='application/json')

    assert resp.status_code == 200
    assert json.loads(resp.data)['ok'] is True

# ── /api/files ────────────────────────────────────────────────────────────────

def test_api_files_returns_structure(client, tmp_path):
    books_out  = tmp_path / 'books_out'
    comics_out = tmp_path / 'comics_out'
    books_out.mkdir()
    comics_out.mkdir()
    (books_out / 'mybook.kepub').write_bytes(b'data')

    with patch.object(bindery_app, 'BOOKS_OUT',  str(books_out)), \
         patch.object(bindery_app, 'COMICS_OUT', str(comics_out)):
        resp = client.get('/api/files')

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert 'books' in data and 'comics' in data
    assert len(data['books'])  == 1
    assert len(data['comics']) == 0
    assert data['books'][0]['name'] == 'mybook.kepub'
    assert 'size'  in data['books'][0]
    assert 'mtime' in data['books'][0]

def test_api_files_empty_dirs(client, tmp_path):
    books_out  = tmp_path / 'books_out'
    comics_out = tmp_path / 'comics_out'
    books_out.mkdir()
    comics_out.mkdir()

    with patch.object(bindery_app, 'BOOKS_OUT',  str(books_out)), \
         patch.object(bindery_app, 'COMICS_OUT', str(comics_out)):
        data = json.loads(client.get('/api/files').data)

    assert data['books']  == []
    assert data['comics'] == []

def test_api_files_nonexistent_dirs(client, tmp_path):
    with patch.object(bindery_app, 'BOOKS_OUT',  str(tmp_path / 'no_books')), \
         patch.object(bindery_app, 'COMICS_OUT', str(tmp_path / 'no_comics')):
        resp = client.get('/api/files')
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data['books']  == []
    assert data['comics'] == []

# ── /api/files/download ───────────────────────────────────────────────────────

def test_api_files_download_rejects_invalid_folder(client):
    resp = client.get('/api/files/download?folder=secret&name=test.epub')
    assert resp.status_code == 400

def test_api_files_download_rejects_empty_name(client, tmp_path):
    with patch.object(bindery_app, 'BOOKS_OUT', str(tmp_path)):
        resp = client.get('/api/files/download?folder=books&name=')
    assert resp.status_code == 400

def test_api_files_download_rejects_path_traversal(client, tmp_path):
    books_out = tmp_path / 'books_out'
    books_out.mkdir()
    with patch.object(bindery_app, 'BOOKS_OUT', str(books_out)):
        resp = client.get('/api/files/download?folder=books&name=../../../etc/passwd')
    assert resp.status_code == 400

def test_api_files_download_returns_404_for_missing_file(client, tmp_path):
    books_out = tmp_path / 'books_out'
    books_out.mkdir()
    with patch.object(bindery_app, 'BOOKS_OUT', str(books_out)):
        resp = client.get('/api/files/download?folder=books&name=ghost.epub')
    assert resp.status_code == 404

def test_api_files_download_serves_file(client, tmp_path):
    books_out = tmp_path / 'books_out'
    books_out.mkdir()
    (books_out / 'test.epub').write_bytes(b'epub content')
    with patch.object(bindery_app, 'BOOKS_OUT', str(books_out)):
        resp = client.get('/api/files/download?folder=books&name=test.epub')
    assert resp.status_code == 200
    assert resp.data == b'epub content'

def test_api_files_download_comics_folder(client, tmp_path):
    comics_out = tmp_path / 'comics_out'
    comics_out.mkdir()
    (comics_out / 'mycomic.epub').write_bytes(b'comic data')
    with patch.object(bindery_app, 'COMICS_OUT', str(comics_out)):
        resp = client.get('/api/files/download?folder=comics&name=mycomic.epub')
    assert resp.status_code == 200
    assert resp.data == b'comic data'


def test_bump_stats_accumulates_and_persists(tmp_path):
    stats_file = tmp_path / 'stats.json'
    with patch.object(processor, 'STATS_FILE', str(stats_file)):
        processor.STATS.update({'converted': 0, 'bytes_saved': 0})
        processor._bump_stats(converted=1, saved=500)
        processor._bump_stats(converted=1, saved=-10)   # a negative saving is clamped to 0
        assert processor.STATS == {'converted': 2, 'bytes_saved': 500}
        processor.STATS.update({'converted': 0, 'bytes_saved': 0})
        processor._load_stats()
        assert processor.STATS == {'converted': 2, 'bytes_saved': 500}
