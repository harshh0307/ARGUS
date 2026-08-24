import hmac, hashlib, json, urllib.request

secret = b"8kQxYbRzRNhhF5JcaqqZIbeZb1/4eflB53+2SjTGo9c="
body = json.dumps({
    "ref": "refs/heads/main",
    "repository": {
        "full_name": "harshh0307/argus-demo",
        "id": 1345076410,
        "owner": {"login": "harshh0307"},
        "name": "argus-demo",
    },
    "after": "abc123",
    "head_commit": {"id": "abc123", "message": "feat: add deprecated API usage"}
}, separators=(",", ":")).encode("utf-8")

sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
print(f"sig={sig}")

req = urllib.request.Request(
    "http://34.239.210.149:8000/api/v1/webhook",
    data=body,
    headers={
        "Content-Type": "application/json",
        "X-Hub-Signature-256": f"sha256={sig}",
        "X-GitHub-Event": "push",
    },
)
resp = urllib.request.urlopen(req)
print(f"Status: {resp.status}")
print(f"Body: {resp.read().decode()}")
