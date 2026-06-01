#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p logs

exec >> logs/start.log 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] user_start.sh begin"
echo "workspace: $(pwd)"

export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8082}"

run_node_app() {
  local script=""
  script="$(node -e "const p=require('./package.json'); const s=p.scripts||{}; console.log(s.start?'start':(s.dev?'dev':''));" 2>/dev/null || true)"
  if [ -z "$script" ]; then
    echo "package.json found, but no start/dev script exists"
    return 1
  fi

  if [ ! -d node_modules ]; then
    if [ -f pnpm-lock.yaml ] && command -v pnpm >/dev/null 2>&1; then
      pnpm install
    elif [ -f yarn.lock ] && command -v yarn >/dev/null 2>&1; then
      yarn install
    elif [ -f package-lock.json ]; then
      npm ci
    else
      npm install
    fi
  fi

  echo "starting node app with npm run ${script} on ${HOST}:${PORT}"
  if [ "$script" = "dev" ]; then
    exec npm run dev -- --host "$HOST" --port "$PORT"
  fi

  exec npm run start -- --host "$HOST" --port "$PORT"
}

if [ -f package.json ] && command -v node >/dev/null 2>&1; then
  run_node_app
elif [ -f app.py ]; then
  echo "starting python app.py on ${HOST}:${PORT}"
  exec python3 app.py
elif [ -f main.py ]; then
  echo "starting python main.py on ${HOST}:${PORT}"
  exec python3 main.py
elif [ -f index.html ]; then
  echo "starting static file server on ${HOST}:${PORT}"
  exec python3 -m http.server "$PORT" --bind "$HOST"
else
  echo "no web app entrypoint found yet; create package.json, app.py, main.py, or index.html to enable auto-start"
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] user_start.sh end"