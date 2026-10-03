#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DATABASE_URL="sqlite:///$PWD/demo-data/retained-demo.db"
export DEMO_MODE=true
export ADMIN_USER_IDS=demo-user
export COLLECTOR_ENABLED=false
export ENABLE_AGENT_UI=true
mkdir -p demo-data
bash scripts/dev.sh
