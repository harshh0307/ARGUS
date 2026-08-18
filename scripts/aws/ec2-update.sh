#!/bin/bash
set -euo pipefail
# Pull latest code + rebuild containers on the EC2 instance.
# Usage (from the instance, after ssh): ./scripts/aws/ec2-update.sh

cd /opt/argus/repo
git pull --ff-only
docker compose up -d --build api worker beat
echo "updated; health: $(curl -sf http://localhost:8000/health || echo DOWN)"
