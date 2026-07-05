"""F5: local sync `source` must be an existing regular tabular file — not a
directory, special file, or a non-data file laundered through a .csv symlink."""

from pathlib import Path

import pytest
from solar_mcp_core.errors import BadInput
from solar_mcp_core.localfile import resolve_local_data_file


def test_accepts_regular_csv(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    p.write_text("a,b\n1,2\n")
    assert resolve_local_data_file(str(p)) == p.resolve()


def test_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(BadInput, match="source"):
        resolve_local_data_file(str(tmp_path / "nope.csv"))


def test_rejects_non_data_extension(tmp_path: Path) -> None:
    # e.g. pointing at a credentials file with no tabular extension
    p = tmp_path / "id_rsa"
    p.write_text("-----BEGIN KEY-----")
    with pytest.raises(BadInput, match="tabular data file"):
        resolve_local_data_file(str(p))


def test_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(BadInput):
        resolve_local_data_file(str(tmp_path))


def test_symlink_to_non_data_file_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "passwd"
    target.write_text("root:x:0:0:")
    link = tmp_path / "innocent.csv"
    link.symlink_to(target)
    # Resolves to `passwd` (no data extension) — a .csv symlink cannot launder it.
    with pytest.raises(BadInput, match="tabular data file"):
        resolve_local_data_file(str(link))
