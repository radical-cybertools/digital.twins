#!/bin/bash
# Round 8b: oldest process matching pgrep -f PATTERN that is not a Dragon
# launcher (as r8/proc_sampler.sh -f), printed as a PID.
for q in $(pgrep -u $USER -f "$1"); do
  tr '\0' ' ' < /proc/$q/cmdline 2>/dev/null | grep -qE '/dragon (-s|-m)|^dragon ' && continue
  [ $q = $$ ] && continue
  echo $q
done | sort -n | head -1
