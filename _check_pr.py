from app.github.client import GitHubClient
from app.core.config import get_settings
s = get_settings()
c = GitHubClient(token=s.github_token)
pr = c.find_open_pull("harshh0307", "argus-cli-demo", "argus/fix")
if pr:
    print(f"PR #{pr} is open")
    info = c.get_pull("harshh0307", "argus-cli-demo", pr)
    print(f"URL: {info.html_url}")
    print(f"head_sha: {info.head_sha}")
    checks = c.check_runs("harshh0307", "argus-cli-demo", info.head_sha)
    for ch in checks:
        print(f"  {ch.name}: {ch.status} / {ch.conclusion}")
else:
    print("no open PR")
