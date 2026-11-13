#!/bin/bash
# Round 8: one JSON line about this node: Dragon native processes (pool
# workers and process tasks run as `_dragon_native_python_process_main`),
# all of the user's processes and threads, memory in MB.
n=$(ps -u $USER -o args= | grep -c '^[^ ]*python[^ ]* -c from dragon.native.process import _dragon_native_python_process_main')
p=$(ps -u $USER -o pid= | wc -l)
t=$(ps -u $USER -L -o lwp= | wc -l)
ma=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
mt=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
echo "{\"host\": \"$(hostname -s)\", \"dragon_native_procs\": $n, \"user_procs\": $p, \"user_threads\": $t, \"mem_avail_mb\": $ma, \"mem_total_mb\": $mt, \"t\": $(date +%s.%N)}"
