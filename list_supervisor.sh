#!/bin/sh
ls /proc/ | grep -E '^[0-9]+$' | while read p; do
  cmd=$(cat /proc/$p/cmdline 2>/dev/null | tr '\0' ' ')
  case "$cmd" in
    *pair-supervisor*|*openclaw*|*node*)
      echo "$p: $cmd"
      ;;
  esac
done
