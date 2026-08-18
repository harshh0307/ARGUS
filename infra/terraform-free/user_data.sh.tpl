#!/bin/bash
set -euo pipefail

exec > /var/log/argus-bootstrap.log 2>&1

export DEBIAN_FRONTEND=noninteractive

echo "== argus free-tier bootstrap =="

apt-get update -y
apt-get install -y docker.io docker-compose-v2 awscli git

systemctl enable --now docker

mkdir -p /opt/argus
cd /opt/argus
git clone ${git_repo} repo
cd repo

echo "== building .env from SSM ${ssm_prefix} =="
: > .env
for name in $$(aws ssm get-parameters-by-path --path "$${ssm_prefix}" --recursive --query 'Parameters[].Name' --output text); do
  key=$${name##*/}
  value=$$(aws ssm get-parameter --name "$$name" --with-decryption --query 'Parameter.Value' --output text)
  echo "$$key=$$value" >> .env
done

cat >> .env <<'EOF'
DATABASE_URL=postgresql+psycopg://argus:argus@postgres:5432/argus
REDIS_URL=redis://redis:6379/0
EOF

echo "== building + starting containers (this takes several minutes on a micro) =="
docker compose up -d --build api worker beat

echo "== waiting for API health =="
for i in $$(seq 1 60); do
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "API healthy after $${i}x10s"
    exit 0
  fi
  sleep 10
done

echo "API never became healthy; see /var/log/argus-bootstrap.log"
exit 1
