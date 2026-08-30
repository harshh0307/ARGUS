from app.ingestion.snapshot_store import SnapshotStore


def test_save_load_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path)
    digest = store.save("github", {"paths": {}}, etag='"abc"')

    assert store.load("github", digest) == {"paths": {}}
    assert store.latest("github") == {"digest": digest, "etag": '"abc"', "format": "json"}


def test_same_content_does_not_duplicate(tmp_path):
    store = SnapshotStore(tmp_path)
    d1 = store.save("github", {"a": 1})
    d2 = store.save("github", {"a": 1})

    assert d1 == d2
    assert store.list_digests("github") == [d1]


def test_unknown_vendor_returns_empty(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.latest("nope") is None
    assert store.list_digests("nope") == []


def test_pin_and_pinned(tmp_path):
    store = SnapshotStore(tmp_path)
    digest = store.pin("github", "old", {"a": 1})

    assert store.pinned("github", "old") == {"digest": digest, "content": {"a": 1}}
    assert store.pinned("github", "nope") is None
