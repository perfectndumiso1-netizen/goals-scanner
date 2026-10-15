from __future__ import annotations

import json

from research.store import Store


def test_store_migrates_versionless_records_and_skips_unknown_future_schemas(tmp_path):
    path = tmp_path / "research.json"
    path.write_text(json.dumps({"version": 1, "records": {
        "legacy": {"fid": "legacy", "kickoff": "2026-10-13 20:00", "facts": []},
        "future": {"schema_version": 99, "fid": "future", "kickoff": "2026-10-13 20:00"},
    }}), encoding="utf-8")
    store = Store(path)
    assert set(store.records) == {"legacy"}
    assert store.records["legacy"]["schema_version"] == 1
    store.put({"fid": "new", "kickoff": "2026-10-13 20:00"})
    store.save()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["records"]["new"]["schema_version"] == 1
