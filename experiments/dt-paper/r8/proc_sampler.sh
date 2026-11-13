#!/bin/bash
# Round 7: sample one process from /proc once a second until it exits.
#   proc_sampler.sh PID            or   proc_sampler.sh -f PATTERN  (oldest match of pgrep -f)
# Line: epoch, VmRSS kB, utime+stime ticks, threads, fds.
if [ "$1" = -f ]; then p=$(pgrep -u $USER -o -f "$2"); echo "# pid $p ($2) on $(hostname -s)" >&2; else p=$1; fi
[ -n "$p" ] || { echo "no process" >&2; exit 1; }
while kill -0 $p 2>/dev/null; do
  echo "$(date +%s.%N) $(awk '/VmRSS/{print $2}' /proc/$p/status) $(awk '{print $14+$15}' /proc/$p/stat) $(awk '/^Threads/{print $2}' /proc/$p/status) $(ls /proc/$p/fd 2>/dev/null | wc -l)"
  sleep 1
done
