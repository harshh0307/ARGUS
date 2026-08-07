import sys
sys.stdout.reconfigure(encoding='utf-8')
from app.github.client import GitHubClient
from app.core.config import get_settings
s = get_settings()
c = GitHubClient(token=s.github_token)
log = c.failure_log("harshh0307", "argus-cli-demo", "6e15ce56d37ff4fb5c1310fefb36850e1baf780a", "check")
if log:
    lines = log.splitlines()
    for i, line in enumerate(lines):
        low = line.lower()
        if any(k in low for k in ["error", "fail", "assert", "traceback", "exception"]):
            start = max(0, i-2)
            end = min(len(lines), i+3)
            for l in lines[start:end]:
                print(l)
            print("---")
