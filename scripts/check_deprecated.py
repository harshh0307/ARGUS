from app.detection.diff import diff_specs
from app.core.config import Settings
import httpx

s = Settings()
old_spec = httpx.get(s.github_old_spec_url, timeout=30).json()
new_spec = httpx.get(s.github_spec_url, timeout=30).json()

changes = diff_specs(old_spec, new_spec)

print(f"Total: {len(changes)}")
print()

# Show all endpoint_removed
for c in changes:
    if c.kind == "endpoint_removed":
        print(f"REMOVED: {c.method.upper()} {c.path}")
        print(f"  Detail: {c.detail[:200]}")
        print()
