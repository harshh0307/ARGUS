from __future__ import annotations

import hashlib
import json
from pathlib import Path


class SnapshotStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def save(self, vendor: str, content: dict, etag: str | None = None) -> str:
        vendor_dir = self.root / vendor
        vendor_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(
            json.dumps(content, sort_keys=True).encode()
        ).hexdigest()[:16]
        path = vendor_dir / f"{digest}.json"
        if not path.exists():
            path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        (vendor_dir / "latest.json").write_text(
            json.dumps({"digest": digest, "etag": etag}), encoding="utf-8"
        )
        return digest

    def latest(self, vendor: str) -> dict | None:
        meta = self.root / vendor / "latest.json"
        if not meta.exists():
            return None
        return json.loads(meta.read_text(encoding="utf-8"))

    def load(self, vendor: str, digest: str) -> dict:
        return json.loads(
            (self.root / vendor / f"{digest}.json").read_text(encoding="utf-8")
        )

    def pin(self, vendor: str, label: str, content: dict) -> str:
        digest = self.save(vendor, content)
        (self.root / vendor / f"{label}.json").write_text(
            json.dumps({"digest": digest}), encoding="utf-8"
        )
        return digest

    def pinned(self, vendor: str, label: str) -> dict | None:
        meta = self.root / vendor / f"{label}.json"
        if not meta.exists():
            return None
        info = json.loads(meta.read_text(encoding="utf-8"))
        return {"digest": info["digest"], "content": self.load(vendor, info["digest"])}

    def list_digests(self, vendor: str) -> list[str]:
        vendor_dir = self.root / vendor
        if not vendor_dir.exists():
            return []
        return sorted(
            p.stem for p in vendor_dir.glob("*.json")
            if p.stem != "latest" and len(p.stem) == 16
        )
