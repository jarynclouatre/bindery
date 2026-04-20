import os
import pytest
from unittest.mock import patch, MagicMock

import processor
from config import DEFAULT_CONFIG


def test_get_output_files_empty_dir(tmp_path):
    assert processor.get_output_files(str(tmp_path)) == []


def test_get_output_files_returns_all_files(tmp_path):
    a = tmp_path / 'a.epub'
    b = tmp_path / 'b.epub'
    a.write_text('a')
    b.write_text('b')
    # Force distinct mtimes so sort order is deterministic
    os.utime(str(a), (1000, 1000))
    os.utime(str(b), (2000, 2000))
    result = processor.get_output_files(str(tmp_path))
    assert len(result) == 2
    assert result[0].endswith('a.epub')
    assert result[1].endswith('b.epub')


def test_get_output_files_ignores_subdirectories(tmp_path):
    (tmp_path / 'file.epub').write_text('x')
    (tmp_path / 'subdir').mkdir()
    result = processor.get_output_files(str(tmp_path))
    assert len(result) == 1


def test_move_output_file_renames_kepub_epub(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    src_file = src / 'mycomic.kepub.epub'
    src_file.write_text('data')
    processor.move_output_file(str(src_file), str(dst))
    assert (dst / 'mycomic.kepub').exists()
    assert not src_file.exists()


def test_move_output_file_leaves_regular_epub_alone(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    src_file = src / 'mybook.epub'
    src_file.write_text('data')
    processor.move_output_file(str(src_file), str(tmp_path / 'dst'))
    assert (tmp_path / 'dst' / 'mybook.epub').exists()


def test_move_output_file_creates_target_dir(tmp_path):
    src = tmp_path / 'file.epub'
    src.write_text('data')
    deep_dst = tmp_path / 'deep' / 'nested' / 'dir'
    processor.move_output_file(str(src), str(deep_dst))
    assert (deep_dst / 'file.epub').exists()


def test_prune_empty_dirs_removes_nested(tmp_path):
    nested = tmp_path / 'a' / 'b' / 'c'
    nested.mkdir(parents=True)
    fake_file = nested / 'file.epub'
    processor.prune_empty_dirs(str(fake_file), str(tmp_path))
    assert not (tmp_path / 'a').exists()


def test_prune_empty_dirs_does_not_remove_base(tmp_path):
    sub = tmp_path / 'sub'
    sub.mkdir()
    fake_file = sub / 'file.epub'
    processor.prune_empty_dirs(str(fake_file), str(tmp_path))
    assert tmp_path.exists()


def test_prune_empty_dirs_stops_at_nonempty_parent(tmp_path):
    nested = tmp_path / 'a' / 'b'
    nested.mkdir(parents=True)
    # Put a file in 'a' so it can't be removed
    (tmp_path / 'a' / 'keep.txt').write_text('x')
    fake_file = nested / 'file.epub'
    processor.prune_empty_dirs(str(fake_file), str(tmp_path))
    assert not (tmp_path / 'a' / 'b').exists()
    assert (tmp_path / 'a').exists()


def test_process_file_flags_failed_when_no_output(tmp_path):
    # KCC exits 0 but produces no output files — source must be renamed .failed,
    # not left in place to be retried on the next scan.
    comics_in = tmp_path / 'comics_in'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake cbz')

    mock_config = dict(DEFAULT_CONFIG)

    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'COMICS_OUT', str(tmp_path / 'comics_out')), \
         patch('processor.load_config', return_value=mock_config), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion', return_value=None):
        # _run_conversion succeeds (no exception) but writes nothing to temp_out
        processor.process_file(str(src), 'comic')

    assert not src.exists(), "source file should have been removed or renamed"
    assert (comics_in / 'test.cbz.failed').exists(), "source should be renamed .failed when no output produced"


def test_build_kcc_cmd_basic(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    filepath = str(tmp_path / 'test.cbz')
    cmd = processor._build_kcc_cmd(config, filepath, '/tmp/out')
    assert 'kcc-c2e' in cmd
    assert '--profile' in cmd
    assert config['kcc_profile'] in cmd
    assert filepath in cmd
    assert '--output' in cmd


def test_build_kcc_cmd_gamma_zero_omitted(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_gamma'] = '0'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--gamma' not in cmd


def test_build_kcc_cmd_gamma_nonzero_included(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_gamma'] = '1.8'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--gamma' in cmd
    assert '1.8' in cmd


def test_build_kcc_cmd_black_borders(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_borders'] = 'black'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--blackborders' in cmd
    assert '--whiteborders' not in cmd


def test_build_kcc_cmd_white_borders(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_borders'] = 'white'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--whiteborders' in cmd
    assert '--blackborders' not in cmd


def test_build_kcc_cmd_no_borders(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_borders'] = 'none'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--blackborders' not in cmd
    assert '--whiteborders' not in cmd


def test_build_kcc_cmd_other_profile_custom_dims(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_profile']      = 'OTHER'
    config['kcc_customwidth']  = '1264'
    config['kcc_customheight'] = '1680'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--customwidth'  in cmd and '1264' in cmd
    assert '--customheight' in cmd and '1680' in cmd


def test_build_kcc_cmd_non_other_profile_ignores_custom_dims(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_profile']      = 'KPW5'
    config['kcc_customwidth']  = '1264'
    config['kcc_customheight'] = '1680'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--customwidth'  not in cmd
    assert '--customheight' not in cmd


def test_build_kcc_cmd_metadatatitle_uses_filename(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_metadatatitle'] = True
    filepath = str(tmp_path / 'My Comic.cbz')
    cmd = processor._build_kcc_cmd(config, filepath, '/tmp/out')
    assert '--title' in cmd
    assert 'My Comic' in cmd


def test_build_kcc_cmd_author_included(tmp_path):
    from config import DEFAULT_CONFIG
    config = dict(DEFAULT_CONFIG)
    config['kcc_author'] = 'Frank Miller'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--author' in cmd
    assert 'Frank Miller' in cmd


def test_process_file_conversion_error(tmp_path):
    comics_in = tmp_path / 'comics_in'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake cbz')

    with patch.object(processor, 'COMICS_IN',  str(comics_in)), \
         patch.object(processor, 'COMICS_OUT', str(tmp_path / 'comics_out')), \
         patch('processor.load_config', return_value=dict(DEFAULT_CONFIG)), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion', side_effect=processor.ConversionError(1)):
        processor.process_file(str(src), 'comic')

    assert not src.exists()
    assert (comics_in / 'test.cbz.failed').exists()


def test_process_file_unexpected_exception(tmp_path):
    comics_in = tmp_path / 'comics_in'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake cbz')

    with patch.object(processor, 'COMICS_IN',  str(comics_in)), \
         patch.object(processor, 'COMICS_OUT', str(tmp_path / 'comics_out')), \
         patch('processor.load_config', return_value=dict(DEFAULT_CONFIG)), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion', side_effect=RuntimeError('disk full')):
        processor.process_file(str(src), 'comic')

    assert not src.exists()
    assert (comics_in / 'test.cbz.failed').exists()


def test_scan_directories_dispatches_comic(tmp_path):
    comics_in = tmp_path / 'comics_in'
    books_in  = tmp_path / 'books_in'
    comics_in.mkdir()
    books_in.mkdir()
    (comics_in / 'test.cbz').write_bytes(b'x')

    dispatched = []
    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'BOOKS_IN',  str(books_in)), \
         patch('processor.threading') as mock_threading:
        def _fake_thread(target, args, daemon): dispatched.append(args); return MagicMock()
        mock_threading.Thread = MagicMock(side_effect=_fake_thread)
        processor.PROCESSING_LOCKS.clear()
        processor.scan_directories()

    assert any(str(comics_in / 'test.cbz') in str(a) for a in dispatched)


def test_scan_directories_skips_failed_files(tmp_path):
    comics_in = tmp_path / 'comics_in'
    books_in  = tmp_path / 'books_in'
    comics_in.mkdir()
    books_in.mkdir()
    (comics_in / 'test.cbz.failed').write_bytes(b'x')

    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'BOOKS_IN',  str(books_in)), \
         patch('processor.threading') as mock_threading:
        processor.PROCESSING_LOCKS.clear()
        processor.scan_directories()

    mock_threading.Thread.assert_not_called()


# ── _notify ───────────────────────────────────────────────────────────────────

def test_notify_no_urls_does_not_raise():
    with patch('processor.load_config', return_value={**DEFAULT_CONFIG, 'apprise_urls': ''}):
        processor._notify('success', 'test.cbz')


def test_notify_success_suppressed_when_disabled():
    mock_apprise = MagicMock()
    with patch('processor.load_config', return_value={
        **DEFAULT_CONFIG,
        'apprise_urls': 'ntfy://example.com/test',
        'notify_on_success': False,
    }), patch.dict('sys.modules', {'apprise': mock_apprise}):
        processor._notify('success', 'test.cbz')
    mock_apprise.Apprise.assert_not_called()


def test_notify_failure_suppressed_when_disabled():
    mock_apprise = MagicMock()
    with patch('processor.load_config', return_value={
        **DEFAULT_CONFIG,
        'apprise_urls': 'ntfy://example.com/test',
        'notify_on_failure': False,
    }), patch.dict('sys.modules', {'apprise': mock_apprise}):
        processor._notify('failure', 'test.cbz')
    mock_apprise.Apprise.assert_not_called()


def test_notify_success_fires_with_correct_title():
    mock_apprise = MagicMock()
    mock_instance = MagicMock()
    mock_apprise.Apprise.return_value = mock_instance
    with patch('processor.load_config', return_value={
        **DEFAULT_CONFIG,
        'apprise_urls': 'ntfy://example.com/test',
        'notify_on_success': True,
    }), patch.dict('sys.modules', {'apprise': mock_apprise}):
        processor._notify('success', 'test.cbz')
    mock_instance.notify.assert_called_once()
    assert mock_instance.notify.call_args.kwargs['title'] == 'Bindery: Conversion complete'


def test_notify_failure_fires_with_error_in_body():
    mock_apprise = MagicMock()
    mock_instance = MagicMock()
    mock_apprise.Apprise.return_value = mock_instance
    with patch('processor.load_config', return_value={
        **DEFAULT_CONFIG,
        'apprise_urls': 'ntfy://example.com/test',
        'notify_on_failure': True,
    }), patch.dict('sys.modules', {'apprise': mock_apprise}):
        processor._notify('failure', 'test.cbz', 'exit 1')
    mock_instance.notify.assert_called_once()
    assert mock_instance.notify.call_args.kwargs['title'] == 'Bindery: Conversion failed'
    assert 'exit 1' in mock_instance.notify.call_args.kwargs['body']


# --- v3.0.2: wait_for_file_ready stability tests ---

def test_wait_for_file_ready_requires_three_stable_reads(tmp_path):
    """Three consecutive identical sizes are required before returning True."""
    from unittest.mock import patch
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [1000, 1000, 1000, 1000]  # set last_size, then 3 matches
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=60) is True


def test_wait_for_file_ready_two_stable_not_enough(tmp_path):
    """Two stable readings followed by timeout must return False."""
    from unittest.mock import patch
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [1000, 1000]  # timeout=3 => 2 loop iterations, never reaches 3
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=3) is False


def test_wait_for_file_ready_resets_on_size_change(tmp_path):
    """A size change mid-sequence resets the stable counter to zero."""
    from unittest.mock import patch
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [1000, 1000, 2000, 2000, 2000, 2000]  # 2 stable, grows, then 3 stable
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=60) is True


def test_wait_for_file_ready_oserror_resets_counter(tmp_path):
    """An OSError during polling resets the stable counter."""
    from unittest.mock import patch
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [OSError("busy"), 1000, 1000, 1000, 1000]  # error, then 3 stable
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=60) is True


# ── preserve_originals / .archive ─────────────────────────────────────────────

def test_scan_directories_skips_archive(tmp_path):
    """Files inside .archive must never be dispatched for conversion."""
    comics_in = tmp_path / 'comics_in'
    books_in  = tmp_path / 'books_in'
    archive   = comics_in / '.archive'
    comics_in.mkdir()
    books_in.mkdir()
    archive.mkdir()
    (archive / 'test.cbz').write_bytes(b'x')

    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'BOOKS_IN',  str(books_in)), \
         patch('processor.threading') as mock_threading:
        processor.PROCESSING_LOCKS.clear()
        processor.scan_directories()

    mock_threading.Thread.assert_not_called()


def test_process_file_preserve_originals(tmp_path):
    """With preserve_originals=True, source file moves to .archive (mirroring
    subfolder structure) instead of being deleted."""
    comics_in      = tmp_path / 'comics_in'
    comics_archive = comics_in / '.archive'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake cbz')

    mock_config = dict(DEFAULT_CONFIG)
    mock_config['preserve_originals'] = True

    with patch.object(processor, 'COMICS_IN',       str(comics_in)), \
         patch.object(processor, 'COMICS_OUT',      str(tmp_path / 'comics_out')), \
         patch.object(processor, 'COMICS_ARCHIVE',  str(comics_archive)), \
         patch('processor.load_config',        return_value=mock_config), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion',     return_value=None), \
         patch('processor.get_output_files',    return_value=[str(tmp_path / 'fake.epub')]), \
         patch('processor.move_output_file',    return_value=None):
        processor.process_file(str(src), 'comic')

    assert not src.exists(), 'source should not remain in comics_in'
    assert (comics_archive / 'test.cbz').exists(), 'source should be in .archive'


def test_scan_directories_skips_dot_folders(tmp_path):
    """Any dot-folder (e.g. .stfolder, .stversions) must be skipped, not just .archive."""
    comics_in  = tmp_path / 'comics_in'
    books_in   = tmp_path / 'books_in'
    stfolder   = comics_in / '.stfolder'
    comics_in.mkdir()
    books_in.mkdir()
    stfolder.mkdir()
    (stfolder / 'test.cbz').write_bytes(b'x')

    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'BOOKS_IN',  str(books_in)), \
         patch('processor.threading') as mock_threading:
        processor.PROCESSING_LOCKS.clear()
        processor.scan_directories()

    mock_threading.Thread.assert_not_called()
