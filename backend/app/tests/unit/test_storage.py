from pathlib import Path
from uuid import uuid4

import pytest

from app.tools.files.storage import build_upload_path, save_context, save_upload


def test_build_upload_path_structure() -> None:
    wid, sid, fid = uuid4(), uuid4(), uuid4()
    path = build_upload_path(wid, sid, fid, "my file.csv")
    parts = path.parts
    assert str(wid) in parts
    assert str(sid) in parts
    assert "original" in parts
    assert path.name.startswith(str(fid))
    assert path.name.endswith("my_file.csv")


def test_save_upload_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.tools.files.storage.settings.LOCAL_STORAGE_DIR", str(tmp_path))
    wid, sid, fid = uuid4(), uuid4(), uuid4()
    stored = save_upload(wid, sid, fid, "data.csv", b"col1,col2\n1,2\n")
    assert Path(stored).exists()
    assert Path(stored).read_bytes() == b"col1,col2\n1,2\n"


def test_save_context_writes_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.tools.files.storage.settings.LOCAL_STORAGE_DIR", str(tmp_path))
    wid, did = uuid4(), uuid4()
    stored = save_context(wid, did, b"Company KPIs\nRevenue target: 1M")
    assert Path(stored).exists()
    assert b"Revenue target" in Path(stored).read_bytes()
