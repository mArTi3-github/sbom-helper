from __future__ import annotations

import json
import tempfile
from pathlib import Path

from purl_resolver.ignore_patterns_store import IgnorePatternsStore


def test_load_returns_empty_list_when_file_missing():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nonexistent.json"
        store = IgnorePatternsStore(path)
        assert store.load() == []


def test_load_returns_patterns():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "patterns.json"
        data = [{"field": "purl", "pattern": "test"}, {"field": "group", "pattern": "test"}]
        path.write_text(json.dumps(data), encoding="utf-8")
        store = IgnorePatternsStore(path)
        assert store.load() == data


def test_save_writes_patterns():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "patterns.json"
        store = IgnorePatternsStore(path)
        data = [{"field": "name", "pattern": "test"}]
        store.save(data)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved == data


def test_save_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "patterns.json"
        path.write_text(json.dumps([{"field": "old", "pattern": "old"}]), encoding="utf-8")
        store = IgnorePatternsStore(path)
        store.save([{"field": "new", "pattern": "new"}])
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved == [{"field": "new", "pattern": "new"}]


def test_load_returns_empty_list_on_corrupt_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "corrupt.json"
        path.write_text("not valid json", encoding="utf-8")
        store = IgnorePatternsStore(path)
        assert store.load() == []


def test_load_returns_empty_list_on_non_list_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "object.json"
        path.write_text('{"key": "value"}', encoding="utf-8")
        store = IgnorePatternsStore(path)
        assert store.load() == []
