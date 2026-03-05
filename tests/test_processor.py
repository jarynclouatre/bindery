import os
import pytest

import processor


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
