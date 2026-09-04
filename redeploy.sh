#!/bin/bash
# MAPNET — redéploiement reproductible du service routing (:8093)
# Usage: git clone <repo> && cd MAPNET && ./redeploy.sh
set -e
cd "$(dirname "$0")"

git fetch origin
git checkout genspark_ai_developer
git pull origin genspark_ai_developer

cd services/routing
python3 -m venv venv 2>/dev/null || true
source venv/bin/activate
pip install --quiet -r requirements.txt

# Stoppe l'instance courante (port 8093)
PID=$(ss -tlnp 2>/dev/null | grep ':8093' | grep -oP 'pid=\K[0-9]+' | head -1 || true)
[ -n "$PID" ] && kill "$PID" 2>/dev/null || true

nohup uvicorn app.main:app --host 0.0.0.0 --port 8093 > /tmp/mapnet_routing.log 2>&1 &
sleep 4
curl -sf http://127.0.0.1:8093/health && echo " -> routing :8093 OK"
