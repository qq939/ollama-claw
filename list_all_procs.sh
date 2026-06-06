#!/bin/sh
for p in $(ls /proc/ 2>/dev/null | grep -E '^[0-9]+$'); do
  if [ -e /proc/$p/cmdline ]; then
    cmd=$(cat /proc/$p/cmdline 2>/dev/null | tr '\0' ' ')
    if [ -n "$cmd" ]; then
      echo "PID $p: $cmd"
    fi
  fi
done
