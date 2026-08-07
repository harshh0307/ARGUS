import sys
sys.stdout.reconfigure(encoding='utf-8')
from app.github.client import GitHubClient
from app.core.config import get_settings
s = get_settings()
c = GitHubClient(token=s.github_token)
f = c.get_file("harshh0307", "argus-cli-demo", "app.py", ref="argus/fix")
if f:
    print(f["content"])
else:
    print("file not found")
