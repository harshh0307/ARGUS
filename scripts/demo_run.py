"""End-to-end demo: register user, vendor, repo, run detection, trigger pipeline."""
import sys
sys.path.insert(0, ".")

from app.core.config import get_settings
s = get_settings()

from app.db.engine import get_engine, init_db, session_factory
from app.db.repository import set_default_engine, upsert_repository
from app.db.models import User, DriftAlert, Vendor, Repository

engine = get_engine(s.database_url)
init_db(engine)
set_default_engine(engine)

session = session_factory(engine)()

# 1. Create admin user
user = User(
    email="admin@argus.dev",
    hashed_password="dummy_hash",
    tenant_id="argus",
    is_admin=True,
)
# Hash the password properly
from app.auth.password import hash_password
user.hashed_password = hash_password("admin123")
session.add(user)
session.commit()
print("Created admin user: admin@argus.dev / admin123")

# 2. Register a demo repo
repo = upsert_repository(session, "octocat", "Hello-World", default_branch="main", vendor_slug="github")
session.commit()
print(f"Registered repo: octocat/Hello-World (id={repo.id})")
session.close()

# 3. Run detection for github
from app.workers.tasks import run_detection
print("\nRunning detection for github...")
result = run_detection("github")
print(f"Result: breaking={result['breaking_count']} additive={result['additive_count']} baselined={result['baselined']}")

# 4. Verify DB state
session = session_factory(engine)()
runs = session.query(DriftAlert).order_by(DriftAlert.id.desc()).all()
print(f"\nDrift alerts in DB: {len(runs)}")
for r in runs:
    print(f"  #{r.id} vendor={r.vendor_slug} type={r.alert_type} severity={r.severity}")

vendors = session.query(Vendor).all()
print(f"Vendors in DB: {len(vendors)}")

repos = session.query(Repository).all()
print(f"Repos in DB: {len(repos)}")
for r in repos:
    print(f"  {r.owner}/{r.name} vendor={r.vendor_slug} active={r.is_active}")

users = session.query(User).all()
print(f"Users in DB: {len(users)}")
for u in users:
    print(f"  {u.email} tenant={u.tenant_id} admin={u.is_admin}")

session.close()
print("\nDone! Start the API with: uvicorn app.api.main:app --reload")
