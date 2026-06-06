#!/bin/sh
ls /proc/ 2>/dev/null | while read p; do
  if [ -d "/proc/$p" ] && [ "$p" -gt 0 ] 2>/dev/null; then
    cmd=$(cat /proc/$p/cmdline 2>/dev/null | tr '\0' ' ')
    if [ -n "$cmd" ]; then
      echo "PID $p: $cmd"
    fi
  fi
done
