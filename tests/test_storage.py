"""Failure-path guarantees for shared JSON persistence."""

import json

import pytest

from prompt_vcs._storage import atomic_write_json


def test_writes_unicode_json_and_creates_parent(tmp_path):
    target = tmp_path / "nested" / "state.json"
    atomic_write_json(target, {"name": "中文"})
    assert json.loads(target.read_text(encoding="utf-8")) == {"name": "中文"}
    assert "中文" in target.read_text(encoding="utf-8")
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize("failure", ["serialization", "flush", "replace"])
@pytest.mark.parametrize("existing", [True, False])
def test_failed_write_preserves_target_and_removes_temp(tmp_path, monkeypatch, failure, existing):
    target = tmp_path / "state.json"
    if existing:
        target.write_text('{"original": true}', encoding="utf-8")

    def fail(*args):
        raise OSError("injected write failure")

    data = {"value": object()} if failure == "serialization" else {"value": 1}
    if failure != "serialization":
        monkeypatch.setattr(
            f"prompt_vcs._storage.os.{'fsync' if failure == 'flush' else 'replace'}", fail
        )
    with pytest.raises((TypeError, OSError)):
        atomic_write_json(target, data)

    if existing:
        assert target.read_text(encoding="utf-8") == '{"original": true}'
    else:
        assert not target.exists()
    assert list(tmp_path.iterdir()) == ([target] if existing else [])
