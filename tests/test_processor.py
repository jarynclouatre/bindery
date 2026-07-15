import json
import os
import pytest
from unittest.mock import patch, MagicMock

import processor
from config import DEFAULT_CONFIG

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

def test_move_output_file_renames_kepub_epub(tmp_path):
    src = tmp_path / 'src'
    dst = tmp_path / 'dst'
    src.mkdir()
    src_file = src / 'mycomic.kepub.epub'
    src_file.write_text('data')
    processor.move_output_file(str(src_file), str(dst))
    assert (dst / 'mycomic.kepub').exists()
    assert not src_file.exists()

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
    config = dict(DEFAULT_CONFIG)
    filepath = str(tmp_path / 'test.cbz')
    cmd = processor._build_kcc_cmd(config, filepath, '/tmp/out')
    assert 'kcc-c2e' in cmd
    assert '--profile' in cmd
    assert config['kcc_profile'] in cmd
    assert filepath in cmd
    assert '--output' in cmd


@pytest.mark.parametrize('key, value, flag, present', [
    ('kcc_borders',      'black', '--blackborders', True),
    ('kcc_borders',      'white', '--whiteborders', True),
    ('kcc_borders',      'none',  '--blackborders', False),
    ('kcc_eraserainbow', True,    '--eraserainbow', True),
    ('kcc_mozjpeg',      True,    '--mozjpeg',      True),
])
def test_build_kcc_cmd_flag_mappings(tmp_path, key, value, flag, present):
    config = dict(DEFAULT_CONFIG)
    config[key] = value
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert (flag in cmd) is present

def test_build_kcc_cmd_gamma_zero_omitted(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config['kcc_gamma'] = '0'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--gamma' not in cmd

def test_build_kcc_cmd_other_profile_custom_dims(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config['kcc_profile']      = 'OTHER'
    config['kcc_customwidth']  = '1264'
    config['kcc_customheight'] = '1680'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--customwidth'  in cmd and '1264' in cmd
    assert '--customheight' in cmd and '1680' in cmd

def test_build_kcc_cmd_non_other_profile_ignores_custom_dims(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config['kcc_profile']      = 'KPW5'
    config['kcc_customwidth']  = '1264'
    config['kcc_customheight'] = '1680'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert '--customwidth'  not in cmd
    assert '--customheight' not in cmd

def test_build_kcc_cmd_metadatatitle_uses_filename(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config['kcc_metadatatitle'] = True
    filepath = str(tmp_path / 'My Comic.cbz')
    cmd = processor._build_kcc_cmd(config, filepath, '/tmp/out')
    assert '--title=My Comic' in cmd

def test_build_kcc_cmd_dash_leading_title_stays_a_value(tmp_path):
    """A file named -Batman.cbz must not read as an option to kcc's argparse."""
    config = dict(DEFAULT_CONFIG)
    config['kcc_metadatatitle'] = True
    cmd = processor._build_kcc_cmd(config, str(tmp_path / '-Batman.cbz'), '/tmp/out')
    assert '--title=-Batman' in cmd

def test_build_kcc_cmd_croppingminimum_percent_to_ratio(tmp_path):
    """The UI stores a percentage; kcc-c2e expects a 0-1 ratio."""
    config = dict(DEFAULT_CONFIG)
    config['kcc_croppingminimum'] = '75'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert cmd[cmd.index('--croppingminimum') + 1] == '0.75'

def test_build_kcc_cmd_legacy_mobi_falls_back_to_epub(tmp_path):
    """Configs saved before MOBI was removed must not produce a broken command."""
    config = dict(DEFAULT_CONFIG)
    config['kcc_format'] = 'MOBI'
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'test.cbz'), '/tmp/out')
    assert cmd[cmd.index('--format') + 1] == 'EPUB'


def test_build_kcc_cmd_comicinfo_reads_metadata_not_filename(tmp_path):
    """ComicInfo mode hands KCC --metadatatitle instead of forcing the filename."""
    config = dict(DEFAULT_CONFIG)
    config['kcc_comicinfo'] = True
    cmd = processor._build_kcc_cmd(config, str(tmp_path / 'Chapter 1 (2).cbz'), '/tmp/out')
    assert cmd[cmd.index('--metadatatitle') + 1] == '1'
    assert not any(a.startswith('--title=') for a in cmd)

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

@pytest.mark.parametrize('filename', ['test.cbz', 'test.pdf'])
def test_scan_directories_dispatches_comic(tmp_path, filename):
    """CBZ and PDF alike dispatch from Comics_in — KCC takes both as input."""
    comics_in = tmp_path / 'comics_in'
    books_in  = tmp_path / 'books_in'
    comics_in.mkdir()
    books_in.mkdir()
    (comics_in / filename).write_bytes(b'x')

    dispatched = []
    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'BOOKS_IN',  str(books_in)), \
         patch('processor.threading') as mock_threading:
        def _fake_thread(target, args, daemon): dispatched.append(args); return MagicMock()
        mock_threading.Thread = MagicMock(side_effect=_fake_thread)
        processor.PROCESSING_LOCKS.clear()
        processor.scan_directories()

    assert any(str(comics_in / filename) in str(a) for a in dispatched)

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

# ── wait_for_file_ready ──────────────────────────────────────────────────────

def test_wait_for_file_ready_requires_three_stable_reads(tmp_path):
    """Three consecutive identical sizes are required before returning True."""
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [1000, 1000, 1000, 1000]  # set last_size, then 3 matches
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=60) is True

def test_wait_for_file_ready_two_stable_not_enough(tmp_path):
    """Two stable readings followed by timeout must return False."""
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [1000, 1000]  # timeout=3 => 2 loop iterations, never reaches 3
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=3) is False

def test_wait_for_file_ready_resets_on_size_change(tmp_path):
    """A size change mid-sequence resets the stable counter to zero."""
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [1000, 1000, 2000, 2000, 2000, 2000]  # 2 stable, grows, then 3 stable
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=60) is True

def test_wait_for_file_ready_oserror_resets_counter(tmp_path):
    """An OSError during polling resets the stable counter."""
    f = tmp_path / "comic.cbz"
    f.write_bytes(b"data")
    sizes = [OSError("busy"), 1000, 1000, 1000, 1000]  # error, then 3 stable
    with patch("processor.os.path.getsize", side_effect=sizes), \
         patch("processor.time.sleep"):
        assert processor.wait_for_file_ready(str(f), timeout=60) is True

# ── originals: delete / archive / keep ────────────────────────────────────────

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

def test_process_file_originals_archive(tmp_path):
    """With originals='archive', source file moves to .archive (mirroring
    subfolder structure) instead of being deleted."""
    comics_in      = tmp_path / 'comics_in'
    comics_archive = comics_in / '.archive'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake cbz')

    mock_config = dict(DEFAULT_CONFIG)
    mock_config['originals'] = 'archive'

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

def test_process_file_originals_keep(tmp_path):
    """With originals='keep', the source stays exactly where it is and is
    recorded in the ledger so the scanner won't re-convert it."""
    comics_in = tmp_path / 'comics_in'
    comics_in.mkdir()
    src = comics_in / 'test.cbz'
    src.write_bytes(b'fake cbz')

    mock_config = dict(DEFAULT_CONFIG)
    mock_config['originals'] = 'keep'

    with patch.object(processor, 'COMICS_IN',         str(comics_in)), \
         patch.object(processor, 'COMICS_OUT',        str(tmp_path / 'comics_out')), \
         patch.object(processor, 'CONVERTED_FILE',    str(tmp_path / 'converted.json')), \
         patch('processor.load_config',        return_value=mock_config), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion',     return_value=None), \
         patch('processor.get_output_files',    return_value=[str(tmp_path / 'fake.epub')]), \
         patch('processor.move_output_file',    return_value=None):
        processor.CONVERTED_LEDGER.clear()
        processor.process_file(str(src), 'comic')

    assert src.exists(), 'source must stay in place'
    assert processor._already_converted(str(src)) is True

def test_process_file_keep_reconvert_replaces_previous_output(tmp_path):
    """When a kept source genuinely changes, the re-convert must replace its own
    earlier output instead of piling up Book_2/Book_3 copies beside it."""
    library = tmp_path / 'library'
    library.mkdir()
    src = library / 'Book.cbz'
    src.write_bytes(b'first version')

    mock_config = dict(DEFAULT_CONFIG)
    mock_config['originals'] = 'keep'

    def fake_output(payload: bytes):
        out_dir = tmp_path / 'produced'
        out_dir.mkdir(exist_ok=True)
        out = out_dir / 'Book.epub'
        out.write_bytes(payload)
        return [str(out)]

    with patch.object(processor, 'COMICS_IN',      str(library)), \
         patch.object(processor, 'COMICS_OUT',     str(library)), \
         patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')), \
         patch('processor.load_config',        return_value=mock_config), \
         patch('processor.wait_for_file_ready', return_value=True), \
         patch('processor._run_conversion',     return_value=None):
        processor.CONVERTED_LEDGER.clear()
        with patch('processor.get_output_files', return_value=fake_output(b'epub one')):
            processor.process_file(str(src), 'comic')
        assert (library / 'Book.epub').read_bytes() == b'epub one'

        src.write_bytes(b'second version, different size')
        with patch('processor.get_output_files', return_value=fake_output(b'epub two')):
            processor.process_file(str(src), 'comic')

    assert (library / 'Book.epub').read_bytes() == b'epub two'
    assert not (library / 'Book_2.epub').exists(), 'old output must be replaced, not stacked'
    assert src.exists()

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

# ── Comics_in folder jobs ─────────────────────────────────────────────────────

def _scan_dispatches(tmp_path, setup):
    """Run scan_directories against a temp tree, return {path: target} of dispatches."""
    comics_in = tmp_path / 'comics_in'
    books_in  = tmp_path / 'books_in'
    comics_in.mkdir()
    books_in.mkdir()
    setup(comics_in)

    dispatched = []
    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'BOOKS_IN',  str(books_in)), \
         patch('processor.threading') as mock_threading:
        def _fake_thread(target, args, daemon): dispatched.append((target, args)); return MagicMock()
        mock_threading.Thread = MagicMock(side_effect=_fake_thread)
        processor.PROCESSING_LOCKS.clear()
        processor.scan_directories()
    return comics_in, {args[0]: target for target, args in dispatched}

def test_scan_directories_image_folder_becomes_folder_job(tmp_path):
    """A top-level folder of images is one bundled KCC volume."""
    def setup(comics_in):
        folder = comics_in / 'Batman'
        folder.mkdir()
        (folder / 'p1.jpg').write_bytes(b'x')
        (folder / 'p2.jpg').write_bytes(b'x')
        (comics_in / 'loose.cbz').write_bytes(b'x')
    comics_in, targets = _scan_dispatches(tmp_path, setup)
    assert targets.get(str(comics_in / 'Batman')) is processor.process_folder
    assert targets.get(str(comics_in / 'loose.cbz')) is processor.process_file

def test_scan_directories_archive_folder_converts_per_file(tmp_path):
    """KCC rejects nested archives, so a folder holding .cbz files must be
    converted file-by-file (preserving structure), never as a folder job."""
    def setup(comics_in):
        folder = comics_in / 'My Series'
        folder.mkdir()
        (folder / 'ch1.cbz').write_bytes(b'x')
        (folder / 'ch2.cbz').write_bytes(b'x')
    comics_in, targets = _scan_dispatches(tmp_path, setup)
    folder = comics_in / 'My Series'
    assert str(folder) not in targets
    assert targets.get(str(folder / 'ch1.cbz')) is processor.process_file
    assert targets.get(str(folder / 'ch2.cbz')) is processor.process_file

def test_scan_directories_bundle_toggle_makes_archive_folder_a_folder_job(tmp_path):
    """With Bundle Chapter Folders on, an archive folder is one bundled job —
    its files must never also dispatch individually (that would double-convert
    and delete sources out from under the bundle)."""
    config = dict(DEFAULT_CONFIG)
    config['bundle_chapter_folders'] = True
    def setup(comics_in):
        folder = comics_in / 'My Series'
        folder.mkdir()
        (folder / 'ch1.cbz').write_bytes(b'x')
        (folder / 'ch2.cbz').write_bytes(b'x')
    with patch('processor.load_config', return_value=config):
        comics_in, targets = _scan_dispatches(tmp_path, setup)
    folder = comics_in / 'My Series'
    assert targets.get(str(folder)) is processor.process_folder
    assert str(folder / 'ch1.cbz') not in targets
    assert str(folder / 'ch2.cbz') not in targets

# ── Chapter bundling ──────────────────────────────────────────────────────────

def _bundle_config(on: bool):
    config = dict(DEFAULT_CONFIG)
    config['bundle_chapter_folders'] = on
    return config

@pytest.mark.parametrize('files, dirs, toggle, expected', [
    (['p1.jpg'], [], False, True),                        # image-only always bundles
    (['p1.jpg'], [], True, True),
    (['ch1.cbz'], [], False, False),                      # archives need the toggle
    (['ch1.cbz'], [], True, True),
    (['ch1.cbz', 'info.json', 'series.nfo'], [], True, True),   # junk tolerated
    ([], [], False, False),                               # empty folder is never a job
    ([], ['.uploading/stale.part'], False, False),        # ...nor one holding only scratch
    (['p1.jpg'], ['.stversions/old.cbz'], False, True),   # hidden archives don't reclassify
    (['ch1.cbz', 'extra.pdf'], [], True, False),          # pdf alongside archives -> per-file
    (['ch1.cbz', 'cover.jpg'], [], True, False),          # loose image alongside -> per-file
    (['book.pdf'], [], True, False),                      # pdf-only -> per-file
])
def test_is_bundle_folder_decision(tmp_path, files, dirs, toggle, expected):
    for name in files:
        (tmp_path / name).write_bytes(b'x')
    for rel in dirs:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'x')
    assert processor._is_bundle_folder(str(tmp_path), _bundle_config(toggle)) is expected

def test_extract_chapter_folder_skips_hidden_directories(tmp_path):
    folder = tmp_path / 'Series'
    folder.mkdir()
    _make_cbz(folder / 'ch1.cbz', ['page1.jpg'])
    hidden = folder / '.stversions'
    hidden.mkdir()
    _make_cbz(hidden / 'old.cbz', ['page1.jpg'])

    temp_parent, kcc_input = processor._extract_chapter_folder(str(folder))
    try:
        assert sorted(os.listdir(kcc_input)) == ['001 - ch1']
    finally:
        import shutil
        shutil.rmtree(temp_parent, ignore_errors=True)

def _make_cbz(path, names):
    import zipfile
    with zipfile.ZipFile(str(path), 'w') as z:
        for n in names:
            z.writestr(n, b'fake page data')

def test_extract_chapter_folder_orders_chapters_naturally(tmp_path):
    folder = tmp_path / 'My Series'
    folder.mkdir()
    for name in ('ch10.cbz', 'ch1.cbz', 'ch2.cbz'):
        _make_cbz(folder / name, ['page1.jpg'])

    temp_parent, kcc_input = processor._extract_chapter_folder(str(folder))
    try:
        assert os.path.basename(kcc_input) == 'My Series'
        chapters = sorted(os.listdir(kcc_input))
        assert chapters == ['001 - ch1', '002 - ch2', '003 - ch10']
        for c in chapters:
            assert os.path.exists(os.path.join(kcc_input, c, 'page1.jpg'))
    finally:
        import shutil
        shutil.rmtree(temp_parent, ignore_errors=True)

def test_extract_chapter_folder_hoists_wrapper_directory(tmp_path):
    """A cbz that is one folder of pages should extract to images at chapter
    level, not chapter/wrapper/images."""
    folder = tmp_path / 'Series'
    folder.mkdir()
    _make_cbz(folder / 'ch1.cbz', ['wrapper/page1.jpg', 'wrapper/page2.jpg'])

    temp_parent, kcc_input = processor._extract_chapter_folder(str(folder))
    try:
        chap = os.path.join(kcc_input, '001 - ch1')
        assert os.path.exists(os.path.join(chap, 'page1.jpg'))
        assert not os.path.exists(os.path.join(chap, 'wrapper'))
    finally:
        import shutil
        shutil.rmtree(temp_parent, ignore_errors=True)

def test_extract_chapter_folder_failure_cleans_temp_and_raises(tmp_path):
    folder = tmp_path / 'Series'
    folder.mkdir()
    (folder / 'ch1.cbz').write_bytes(b'not a real archive')

    with patch('processor.uuid') as mock_uuid:
        mock_uuid.uuid4.return_value.hex = 'bundletest'
        with pytest.raises(ValueError):
            processor._extract_chapter_folder(str(folder))
    assert not os.path.exists('/tmp/bundletest_bundle')

# ── Device profiles ───────────────────────────────────────────────────────────

def test_profile_for_path_matches_only_created_profiles(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config['profiles'] = {'kobo': {}}
    with patch.object(processor, 'COMICS_IN', str(tmp_path)):
        assert processor._profile_for_path(str(tmp_path / 'kobo' / 'x.cbz'), config) == 'kobo'
        assert processor._profile_for_path(str(tmp_path / 'kobo' / 'Series' / 'x.cbz'), config) == 'kobo'
        assert processor._profile_for_path(str(tmp_path / 'x.cbz'), config) is None
        assert processor._profile_for_path(str(tmp_path / 'Marvel' / 'x.cbz'), config) is None

def test_config_for_path_applies_profile_kcc_only(tmp_path):
    config = dict(DEFAULT_CONFIG)
    config['profiles'] = {'kobo': {'kcc_profile': 'KPW5', 'kcc_manga_style': True}}
    config['originals'] = 'keep'
    with patch.object(processor, 'COMICS_IN', str(tmp_path)), \
         patch('processor.load_config', return_value=config):
        inside  = processor._config_for_path(str(tmp_path / 'kobo' / 'x.cbz'))
        outside = processor._config_for_path(str(tmp_path / 'x.cbz'))
    assert inside['kcc_profile'] == 'KPW5'
    assert inside['kcc_manga_style'] is True
    assert inside['originals'] == 'keep'
    assert outside['kcc_profile'] == DEFAULT_CONFIG['kcc_profile']
    assert outside['kcc_manga_style'] is False

def test_scan_directories_profile_folder_is_a_root_not_a_job(tmp_path):
    """A profile folder is a drop target with its own settings: files inside
    dispatch per-file, folders inside become folder jobs, and the profile
    folder itself must never convert as one giant volume."""
    config = dict(DEFAULT_CONFIG)
    config['profiles'] = {'kobo': {}}
    def setup(comics_in):
        kobo = comics_in / 'kobo'
        kobo.mkdir()
        (kobo / 'x.cbz').write_bytes(b'x')
        series = kobo / 'Batman'
        series.mkdir()
        (series / 'p1.jpg').write_bytes(b'x')
    with patch('processor.load_config', return_value=config):
        comics_in, targets = _scan_dispatches(tmp_path, setup)
    kobo = comics_in / 'kobo'
    assert str(kobo) not in targets
    assert targets.get(str(kobo / 'x.cbz')) is processor.process_file
    assert targets.get(str(kobo / 'Batman')) is processor.process_folder

def test_folder_quiet_secs_follows_timeout_with_floor():
    assert processor._folder_quiet_secs({'file_wait_timeout': 300}) == 300
    assert processor._folder_quiet_secs({'file_wait_timeout': 10}) == 30
    assert processor._folder_quiet_secs({'file_wait_timeout': 'junk'}) == 60
    assert processor._folder_quiet_secs({}) == 60

def test_scan_directories_never_descends_into_failed_folders(tmp_path):
    """Archives inside a <name>.failed folder must not be converted — that
    silently consumes a failed job's source files."""
    def setup(comics_in):
        failed = comics_in / 'My Series.failed'
        failed.mkdir()
        (failed / 'ch1.cbz').write_bytes(b'x')
    _, targets = _scan_dispatches(tmp_path, setup)
    assert targets == {}

def test_process_folder_success_removes_source(tmp_path):
    comics_in = tmp_path / 'comics_in'
    folder    = comics_in / 'Batman'
    comics_in.mkdir()
    folder.mkdir()
    (folder / 'p1.jpg').write_bytes(b'x')
    fake_out = tmp_path / 'fake.epub'
    fake_out.write_bytes(b'epub')

    with patch.object(processor, 'COMICS_OUT', str(tmp_path / 'out')), \
         patch('processor.load_config', return_value=dict(DEFAULT_CONFIG)), \
         patch('processor._is_dir_stable', return_value=True), \
         patch('processor._run_conversion', return_value=None), \
         patch('processor.get_output_files', return_value=[str(fake_out)]), \
         patch('processor.move_output_file', return_value=None):
        processor.process_folder(str(folder))

    assert not folder.exists()
    job = list(processor.JOB_REGISTRY.values())[0]
    assert job['state'] == 'success'
    assert job['src_bytes'] == 1
    assert job['out_bytes'] == 4

def test_process_folder_originals_archive(tmp_path):
    comics_in = tmp_path / 'comics_in'
    archive   = comics_in / '.archive'
    folder    = comics_in / 'Batman'
    comics_in.mkdir()
    folder.mkdir()
    (folder / 'p1.jpg').write_bytes(b'x')
    fake_out = tmp_path / 'fake.epub'
    fake_out.write_bytes(b'epub')
    config = dict(DEFAULT_CONFIG)
    config['originals'] = 'archive'

    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'COMICS_ARCHIVE', str(archive)), \
         patch.object(processor, 'COMICS_OUT', str(tmp_path / 'out')), \
         patch('processor.load_config', return_value=config), \
         patch('processor._is_dir_stable', return_value=True), \
         patch('processor._run_conversion', return_value=None), \
         patch('processor.get_output_files', return_value=[str(fake_out)]), \
         patch('processor.move_output_file', return_value=None):
        processor.process_folder(str(folder))

    assert not folder.exists()
    assert (archive / 'Batman' / 'p1.jpg').exists()

def test_process_folder_originals_keep(tmp_path):
    """With originals='keep', the folder job is left in place and recorded."""
    comics_in = tmp_path / 'comics_in'
    folder    = comics_in / 'Batman'
    comics_in.mkdir()
    folder.mkdir()
    (folder / 'p1.jpg').write_bytes(b'x')
    fake_out = tmp_path / 'fake.epub'
    fake_out.write_bytes(b'epub')
    config = dict(DEFAULT_CONFIG)
    config['originals'] = 'keep'

    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'COMICS_OUT', str(tmp_path / 'out')), \
         patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')), \
         patch('processor.load_config', return_value=config), \
         patch('processor._is_dir_stable', return_value=True), \
         patch('processor._run_conversion', return_value=None), \
         patch('processor.get_output_files', return_value=[str(fake_out)]), \
         patch('processor.move_output_file', return_value=None):
        processor.CONVERTED_LEDGER.clear()
        processor.process_folder(str(folder))

    assert folder.exists(), 'folder must stay in place'
    assert (folder / 'p1.jpg').exists()
    assert processor._already_converted(str(folder)) is True

def test_process_folder_failure_keeps_earlier_failed_folder(tmp_path):
    """A second failure must not collide with (or destroy) an existing .failed folder."""
    comics_in = tmp_path / 'comics_in'
    folder    = comics_in / 'Batman'
    old       = comics_in / 'Batman.failed'
    comics_in.mkdir()
    folder.mkdir()
    old.mkdir()
    (old / 'keep.jpg').write_bytes(b'old attempt')
    (folder / 'p1.jpg').write_bytes(b'x')

    with patch.object(processor, 'COMICS_OUT', str(tmp_path / 'out')), \
         patch('processor.load_config', return_value=dict(DEFAULT_CONFIG)), \
         patch('processor._is_dir_stable', return_value=True), \
         patch('processor._run_conversion', side_effect=processor.ConversionError(1)):
        processor.process_folder(str(folder))

    assert (old / 'keep.jpg').exists()
    assert (comics_in / 'Batman_2.failed' / 'p1.jpg').exists()
    job = list(processor.JOB_REGISTRY.values())[0]
    assert job['state'] == 'failed'
    assert job['failed_path'] == str(comics_in / 'Batman_2.failed')

def test_strip_leading_dash_renames_and_updates_job(tmp_path):
    """KCC runs 7z on the bare basename, so -Batman.cbz reads as a switch there."""
    src = tmp_path / '-Batman.cbz'
    src.write_bytes(b'x')
    with patch.object(processor, 'JOBS_FILE', str(tmp_path / 'jobs.json')):
        job_id  = processor._register_job(str(src), 'comic')
        newpath = processor._strip_leading_dash(str(src), job_id)
    assert os.path.basename(newpath) == 'Batman.cbz'
    assert (tmp_path / 'Batman.cbz').exists()
    assert not src.exists()
    assert processor.JOB_REGISTRY[job_id]['filepath'] == newpath

# ── converted ledger (keep-in-place guard) ────────────────────────────────────

def test_converted_ledger_marks_and_recognizes(tmp_path):
    src = tmp_path / 'Book.cbz'
    src.write_bytes(b'hello')
    with patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')):
        processor.CONVERTED_LEDGER.clear()
        assert processor._already_converted(str(src)) is False
        processor._mark_converted(str(src))
        assert processor._already_converted(str(src)) is True

def test_converted_ledger_detects_changed_source(tmp_path):
    """A replaced copy (different size/mtime) is not treated as already done."""
    src = tmp_path / 'Book.cbz'
    src.write_bytes(b'hello')
    with patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')):
        processor.CONVERTED_LEDGER.clear()
        processor._mark_converted(str(src))
        assert processor._already_converted(str(src)) is True
        src.write_bytes(b'a bigger, different payload')
        assert processor._already_converted(str(src)) is False

def test_converted_ledger_ignores_timestamp_only_touch(tmp_path):
    """A library manager touching a converted file (same bytes, new mtime) must
    not re-trigger conversion — that loops forever when Comics_out is the same
    folder. The stored signature refreshes so the entry stays current."""
    src = tmp_path / 'Book.cbz'
    src.write_bytes(b'hello')
    with patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')):
        processor.CONVERTED_LEDGER.clear()
        processor._mark_converted(str(src))
        os.utime(str(src), (1000000000, 1000000000))
        assert processor._already_converted(str(src)) is True
        assert processor._already_converted(str(src)) is True, 'refreshed sig must hold'

def test_converted_ledger_accepts_legacy_string_entries(tmp_path):
    """4.1.x stored a bare signature string; those entries must keep gating."""
    src = tmp_path / 'Book.cbz'
    src.write_bytes(b'hello')
    ledger_file = tmp_path / 'converted.json'
    ledger_file.write_text(json.dumps({str(src): processor._ledger_signature(str(src))}))
    with patch.object(processor, 'CONVERTED_FILE', str(ledger_file)):
        processor.CONVERTED_LEDGER.clear()
        processor._load_converted_ledger()
        assert processor._already_converted(str(src)) is True
        os.utime(str(src), (1000000000, 1000000000))
        assert processor._already_converted(str(src)) is True

def test_converted_ledger_persists_across_reload(tmp_path):
    src = tmp_path / 'Book.cbz'
    src.write_bytes(b'hello')
    with patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')):
        processor.CONVERTED_LEDGER.clear()
        processor._mark_converted(str(src))
        processor.CONVERTED_LEDGER.clear()
        processor._load_converted_ledger()
        assert processor._already_converted(str(src)) is True

def test_ledger_signature_folder_tracks_contents_ignores_dot_dirs(tmp_path):
    folder = tmp_path / 'Series'
    folder.mkdir()
    (folder / 'ch1.cbz').write_bytes(b'x')
    sig1 = processor._ledger_signature(str(folder))
    (folder / 'ch2.cbz').write_bytes(b'yy')
    sig2 = processor._ledger_signature(str(folder))
    assert sig1 != sig2, 'gaining a chapter must change the signature'
    stfolder = folder / '.stfolder'
    stfolder.mkdir()
    (stfolder / 'junk').write_bytes(b'zzz')
    assert processor._ledger_signature(str(folder)) == sig2, 'dot-dirs must not count'

def test_scan_skips_already_converted_in_keep_mode(tmp_path):
    """In keep mode the scanner does not re-dispatch a source the ledger already
    knows, but does re-dispatch one that changed on disk."""
    comics_in = tmp_path / 'comics_in'
    books_in  = tmp_path / 'books_in'
    comics_in.mkdir()
    books_in.mkdir()
    src = comics_in / 'Book.cbz'
    src.write_bytes(b'hello')

    config = dict(DEFAULT_CONFIG)
    config['originals'] = 'keep'

    def run(mark):
        dispatched = []
        with patch.object(processor, 'COMICS_IN', str(comics_in)), \
             patch.object(processor, 'BOOKS_IN',  str(books_in)), \
             patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')), \
             patch('processor.load_config', return_value=config), \
             patch('processor.threading') as mock_threading:
            def _fake(target, args, daemon): dispatched.append(args[0]); return MagicMock()
            mock_threading.Thread = MagicMock(side_effect=_fake)
            processor.PROCESSING_LOCKS.clear()
            if mark:
                processor._mark_converted(str(src))
            processor.scan_directories()
        return dispatched

    processor.CONVERTED_LEDGER.clear()
    assert str(src) in run(mark=False), 'unconverted source should dispatch'
    assert str(src) not in run(mark=True), 'converted, unchanged source should be skipped'
    src.write_bytes(b'a different, larger payload')
    assert str(src) in run(mark=False), 'a changed source should dispatch again'

def test_scan_ignores_ledger_when_not_keep_mode(tmp_path):
    """delete/archive modes always dispatch — the ledger guard is keep-only."""
    comics_in = tmp_path / 'comics_in'
    books_in  = tmp_path / 'books_in'
    comics_in.mkdir()
    books_in.mkdir()
    src = comics_in / 'Book.cbz'
    src.write_bytes(b'hello')

    config = dict(DEFAULT_CONFIG)
    config['originals'] = 'archive'

    dispatched = []
    with patch.object(processor, 'COMICS_IN', str(comics_in)), \
         patch.object(processor, 'BOOKS_IN',  str(books_in)), \
         patch.object(processor, 'CONVERTED_FILE', str(tmp_path / 'converted.json')), \
         patch('processor.load_config', return_value=config), \
         patch('processor.threading') as mock_threading:
        def _fake(target, args, daemon): dispatched.append(args[0]); return MagicMock()
        mock_threading.Thread = MagicMock(side_effect=_fake)
        processor.PROCESSING_LOCKS.clear()
        processor.CONVERTED_LEDGER.clear()
        processor._mark_converted(str(src))
        processor.scan_directories()

    assert str(src) in dispatched, 'archive mode must ignore the ledger'
