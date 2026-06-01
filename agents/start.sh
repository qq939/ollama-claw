#!/bin/bash
set -e

cd "${PROJECT_PATH:-$(pwd)}"
mkdir -p logs

if [ -f /usr/local/bin/ask_server.js ]; then
    ASK_PORT="${ASK_PORT:-8081}" ASK_HOST="${ASK_HOST:-127.0.0.1}" \
        nohup node /usr/local/bin/ask_server.js >> logs/ask_server.log 2>&1 &
elif [ -f ask_server.js ]; then
    ASK_PORT="${ASK_PORT:-8081}" ASK_HOST="${ASK_HOST:-127.0.0.1}" \
        nohup node ask_server.js >> logs/ask_server.log 2>&1 &
fi

if [ -f /usr/local/bin/server.js ]; then
    SERVER_PORT="${SERVER_PORT:-8082}" ASK_UPSTREAM_PORT="${ASK_UPSTREAM_PORT:-8081}" \
        nohup node /usr/local/bin/server.js >> logs/server.log 2>&1 &
elif [ -f server.js ]; then
    SERVER_PORT="${SERVER_PORT:-8082}" ASK_UPSTREAM_PORT="${ASK_UPSTREAM_PORT:-8081}" \
        nohup node server.js >> logs/server.log 2>&1 &
fi

if [ -f user_start.sh ] && [ -s user_start.sh ]; then
    chmod +x user_start.sh
    PORT="${APP_PORT:-3000}" ./user_start.sh &
fi

wait
