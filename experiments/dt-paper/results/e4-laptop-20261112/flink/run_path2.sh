#!/bin/bash
# Full E4 Flink baseline: path 1 (stop-with-savepoint + resubmit), path 2 (broadcast state). Assumes ./cluster.sh start.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); R=${1:-$H/../results/r1}; mkdir -p $R
cd $H
PY="python3 -I"
{ date -Iseconds; uname -a; lscpu | grep -E 'Model name|^CPU\(s\)|Thread|max MHz'; free -g | head -2; uptime
  /usr/lib/jvm/java-17-openjdk-amd64/bin/java -version 2>&1; curl -s localhost:8081/config; echo; cat conf/config.yaml | sed 1,4d; } > $R/env.txt
# path 2 (model stream via non-blocking DataGeneratorSource rate limiter), repeats outermost
B="driver.py bcast --dur 15 --warmup 4"
for r in 1 2 3 4 5; do
  for u in 0 1 10 100; do
    $PY $B --out $R/bc-lat-r2000-u$u-r$r --rate 2000 --upd $u
    $PY $B --out $R/bc-max-u$u-r$r --rate 0 --upd $u --sample 1000
  done
done
for r in 1 2 3; do
  for u in 0 1 10 100; do
    $PY $B --out $R/bc-work500-sat-u$u-r$r --rate 0 --upd $u --work-us 500
    $PY $B --out $R/bc-work500-sat-unaligned-u$u-r$r --rate 0 --upd $u --work-us 500 --unaligned
    $PY $B --out $R/bc-work500-r1800-u$u-r$r --rate 1800 --upd $u --work-us 500
  done
  for u in 0 100; do
    $PY $B --out $R/bc-max-p4-u$u-r$r --rate 0 --upd $u --sample 1000 --p 4
  done
done
$PY analyze_bcast.py $R/bc-* > $R/bcast-points.txt
date -Iseconds >> $R/env.txt
echo DONE
