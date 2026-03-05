import os
import time
import zipfile
import pytest
from unittest.mock import patch

import raw_processor


def test_is_folder_stable_with_old_files(tmp_path):
    f = tmp_path / 'page001.jpg'
    f.write_bytes(b'img')
    old_time = time.time() - 60
    os.utime(str(f), (old_time, old_time))
    assert raw_processor.is_folder_stable(str(tmp_path)) is True


def test_is_folder_stable_with_new_files(tmp_path):
    f = tmp_path / 'page001.jpg'
    f.write_bytes(b'img')
    assert raw_processor.is_folder_stable(str(tmp_path)) is False


def test_is_folder_stable_empty_folder(tmp_path):
    assert raw_processor.is_folder_stable(str(tmp_path)) is False


def test_is_folder_stable_missing_folder(tmp_path):
    assert raw_processor.is_folder_stable(str(tmp_path / 'nonexistent')) is False


def test_available_cbz_path_no_collision(tmp_path):
    with patch.object(raw_processor, 'COMICS_IN', str(tmp_path)):
        result = raw_processor._available_cbz_path('Batman')
    assert result == str(tmp_path / 'Batman.cbz')


def test_available_cbz_path_with_one_collision(tmp_path):
    (tmp_path / 'Batman.cbz').write_bytes(b'x')
    with patch.object(raw_processor, 'COMICS_IN', str(tmp_path)):
        result = raw_processor._available_cbz_path('Batman')
    assert result == str(tmp_path / 'Batman_2.cbz')


def test_available_cbz_path_with_multiple_collisions(tmp_path):
    (tmp_path / 'Batman.cbz').write_bytes(b'x')
    (tmp_path / 'Batman_2.cbz').write_bytes(b'x')
    with patch.object(raw_processor, 'COMICS_IN', str(tmp_path)):
        result = raw_processor._available_cbz_path('Batman')
    assert result == str(tmp_path / 'Batman_3.cbz')


def test_available_dest_path_no_collision(tmp_path):
    result = raw_processor._available_dest_path(str(tmp_path), 'Batman')
    assert result == str(tmp_path / 'Batman')


def test_available_dest_path_with_collision(tmp_path):
    (tmp_path / 'Batman').mkdir()
    result = raw_processor._available_dest_path(str(tmp_path), 'Batman')
    assert result == str(tmp_path / 'Batman_2')


def _patch_dirs(tmp_path):
    comics_in   = tmp_path / 'comics_in'
    processed   = tmp_path / 'processed'
    unprocessed = tmp_path / 'unprocessed'
    comics_in.mkdir()
    return (
        patch.object(raw_processor, 'COMICS_IN',              str(comics_in)),
        patch.object(raw_processor, 'COMICS_RAW_PROCESSED',   str(processed)),
        patch.object(raw_processor, 'COMICS_RAW_UNPROCESSED', str(unprocessed)),
        comics_in, processed, unprocessed,
    )


def test_process_raw_folder_rejects_subfolders(tmp_path):
    p1, p2, p3, comics_in, processed, unprocessed = _patch_dirs(tmp_path)
    source = tmp_path / 'Batman'
    source.mkdir()
    (source / 'chapter1').mkdir()
    (source / 'page001.jpg').write_bytes(b'img')
    with p1, p2, p3:
        raw_processor.process_raw_folder(str(source))
    assert not source.exists()
    assert (unprocessed / 'Batman').exists()
    assert list(comics_in.iterdir()) == []


def test_process_raw_folder_rejects_no_images(tmp_path):
    p1, p2, p3, comics_in, processed, unprocessed = _patch_dirs(tmp_path)
    source = tmp_path / 'Batman'
    source.mkdir()
    (source / 'readme.txt').write_text('hello')
    with p1, p2, p3:
        raw_processor.process_raw_folder(str(source))
    assert not source.exists()
    assert (unprocessed / 'Batman').exists()
    assert list(comics_in.iterdir()) == []


def test_process_raw_folder_creates_valid_cbz(tmp_path):
    p1, p2, p3, comics_in, processed, unprocessed = _patch_dirs(tmp_path)
    source = tmp_path / 'Batman Issue 1'
    source.mkdir()
    (source / 'page001.jpg').write_bytes(b'img1')
    (source / 'page002.jpg').write_bytes(b'img2')
    (source / 'page003.png').write_bytes(b'img3')
    with p1, p2, p3:
        raw_processor.process_raw_folder(str(source))
    assert not source.exists()
    assert (processed / 'Batman Issue 1').exists()
    cbz = comics_in / 'Batman Issue 1.cbz'
    assert cbz.exists()
    with zipfile.ZipFile(str(cbz)) as zf:
        names = sorted(zf.namelist())
    assert names == ['page001.jpg', 'page002.jpg', 'page003.png']


def test_process_raw_folder_ignores_junk_files(tmp_path):
    p1, p2, p3, comics_in, processed, unprocessed = _patch_dirs(tmp_path)
    source = tmp_path / 'Batman'
    source.mkdir()
    (source / 'page001.jpg').write_bytes(b'img1')
    (source / '.DS_Store').write_bytes(b'junk')
    (source / 'Thumbs.db').write_bytes(b'junk')
    with p1, p2, p3:
        raw_processor.process_raw_folder(str(source))
    cbz = comics_in / 'Batman.cbz'
    assert cbz.exists()
    with zipfile.ZipFile(str(cbz)) as zf:
        names = zf.namelist()
    assert names == ['page001.jpg']


def test_process_raw_folder_handles_cbz_collision(tmp_path):
    p1, p2, p3, comics_in, processed, unprocessed = _patch_dirs(tmp_path)
    (comics_in / 'Batman.cbz').write_bytes(b'existing')
    source = tmp_path / 'Batman'
    source.mkdir()
    (source / 'page001.jpg').write_bytes(b'img1')
    with p1, p2, p3:
        raw_processor.process_raw_folder(str(source))
    assert (comics_in / 'Batman_2.cbz').exists()
    assert (comics_in / 'Batman.cbz').read_bytes() == b'existing'


def test_scan_skips_processed_and_unprocessed_dirs(tmp_path):
    (tmp_path / 'processed').mkdir()
    (tmp_path / 'unprocessed').mkdir()
    with patch.object(raw_processor, 'COMICS_RAW', str(tmp_path)), \
         patch('raw_processor.is_folder_stable', return_value=True), \
         patch('raw_processor.threading') as mock_threading:
        raw_processor.scan_raw_directories()
    mock_threading.Thread.assert_not_called()


def test_scan_skips_unstable_folders(tmp_path):
    (tmp_path / 'Batman').mkdir()
    with patch.object(raw_processor, 'COMICS_RAW', str(tmp_path)), \
         patch('raw_processor.is_folder_stable', return_value=False), \
         patch('raw_processor.threading') as mock_threading:
        raw_processor.scan_raw_directories()
    mock_threading.Thread.assert_not_called()
