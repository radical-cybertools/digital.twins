#!/bin/bash
# Round 7: sample one process from /proc once a second until it exits.
#   proc_sampler.sh PID            or   proc_sampler.sh -f PATTERN  (oldest match of pgrep -f)
# Line: epoch, VmRSS kB, utime+stime ticks, threads, fds.
if [ "$1" = -f ]; then
  # oldest match that is not a Dragon launcher: under `dragon -s prog`, the
  # launcher's own command line names prog too (round 8, R8-2 sampled it)
  p=$(for q in $(pgrep -u $USER -f "$2"); do
        tr '\0' ' ' < /proc/$q/cmdline 2>/dev/null | grep -qE '/dragon (-s|-m)|^dragon ' && continue
        [ $q = $$ ] && continue
        echo $q
      done | sort -n | head -1)
  echo "# pid $p ($2) on $(hostname -s): $(tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | cut -c1-160)" >&2
else p=$1; fi
[ -n "$p" ] || { echo "no process" >&2; exit 1; }
while kill -0 $p 2>/dev/null; do
  echo "$(date +%s.%N) $(awk '/VmRSS/{print $2}' /proc/$p/status) $(awk '{print $14+$15}' /proc/$p/stat) $(awk '/^Threads/{print $2}' /proc/$p/status) $(ls /proc/$p/fd 2>/dev/null | wc -l)"
  sleep 1
done
