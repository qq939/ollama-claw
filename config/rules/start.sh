#!/bin/bash
set -e

mkdir -p logs

if [ -f /usr/local/bin/ask_server.js ]; then
    ASK_PORT="${ASK_PORT:-8081}" ASK_HOST="${ASK_HOST:-0.0.0.0}" \
        nohup node /usr/local/bin/ask_server.js >> logs/ask_server.log 2>&1 &
elif [ -f ask_server.js ]; then
    ASK_PORT="${ASK_PORT:-8081}" ASK_HOST="${ASK_HOST:-0.0.0.0}" \
        nohup node ask_server.js >> logs/ask_server.log 2>&1 &
fi

if [ -f user_start.sh ] && [ -s user_start.sh ]; then
    chmod +x user_start.sh
    ./user_start.sh &
fi

wait
