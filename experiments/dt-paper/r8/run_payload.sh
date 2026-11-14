#!/bin/bash
# Round 8, R8-A: payload size, three paths, cluster and wide area.
#SBATCH -J r8-a
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 01:00:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-a-%j.out
#   sbatch -A m5290 -q regular r8/run_payload.sh
# Node 0: broker (--plugins dt, throwaway TLS) and the clients; node 1: one
# Dragon endpoint (dragon_native, whole node).  Wide area: the radical.3
# broker on :8010 with its endpoint r3_site (read-only use of the default
# credentials in ~/.radical/orbit, as round 2 S2; never port 8011).
#  streams  e1-overhead/bench_streams.py --payload S: zmq (embedded broker,
#           local floor) and orbit eventing on the cluster broker, then orbit
#           through radical.3; S = 100 B .. 64 MB, fewer messages for big S
#  echo     r8/bench_echo.py: a function task taking and returning S bytes
#           (1 KB .. 16 MB, around the 2 MiB return limit), both brokers
#  publish  e4-hot-swap/bench_model_update.py on the cluster endpoint,
#           dragon_native: by value 0.2 / 10 / 100 MB, by path 10 MB / 1 GB
#           (a file in $W/models on /pscratch, which the endpoint shares);
#           by value through radical.3 (by path is not possible there: the
#           file would have to be on radical.3's file system)
# Knobs: STEPS ("streams echo publish"), PORT (8201).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-a}; mkdir -p $R $W/models
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
N1=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$" | sed -n 1p)
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8201}
URL=https://$IP0:$PORT
R3=https://95.217.193.116:8010
echo "node0 $N0 ($IP0) endpoint $N1  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8a-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8a-$J; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r8a-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
export RADICAL_ORBIT_LOG_FILE=$L/client-r8a-$J.log
EPN=r8a_ep
srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w $N1 --export=ALL \
  env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8a-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
      RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
      DT_TEST_ENDPOINT_TAG=$EPN \
  bash -c "ulimit -Sn \$(ulimit -Hn); exec dragon -s $(command -v radical-orbit-endpoint.py) -n $EPN -u $URL -p default --tunnel none" \
  > $R/endpoint.console-$J.log 2>&1 &
EP=$!
echo "endpoint up after $(timeout 330 python $X/r8/wait_endpoint.py $URL $EPN 300) s"
R3OK=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' $R3/)
echo "radical.3:8010 http $R3OK"
r3() {  # run a command against radical.3 with its default credentials
  ( unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
    export RADICAL_ORBIT_LOG_FILE=$L/client-r8a-r3-$J.log
    "$@" )
}
msgs() {  # size -> "messages burst"
  if [ $1 -ge 16000000 ]; then echo "10 10"; elif [ $1 -ge 1000000 ]; then echo "50 50"; else echo "200 200"; fi
}
for s in ${STEPS:-streams echo publish}; do
  case $s in
    streams)
      for S in 100 1024 102400 1048576 16777216 67108864; do
        read m b <<< "$(msgs $S)"
        f=$R/streams-cluster-$S-$J-$D.log
        timeout 600 python $X/e1-overhead/bench_streams.py both --broker $URL --payload $S \
          --messages $m --burst $b > $f 2>&1; echo "streams cluster $S rc=$? $(grep -E 'p50|burst' $f | tr '\n' '|' | cut -c1-300)"
        if [ "$R3OK" = 200 ]; then
          f=$R/streams-r3-$S-$J-$D.log
          r3 timeout 600 python $X/e1-overhead/bench_streams.py orbit --broker $R3 --payload $S \
            --messages $m --burst $b > $f 2>&1; echo "streams r3 $S rc=$? $(grep -E 'p50|burst' $f | tr '\n' '|' | cut -c1-300)"
        fi
      done ;;
    echo)
      timeout 1200 python $X/r8/bench_echo.py --broker $URL --endpoint $EPN \
        --out $R/echo-cluster-$J-$D.json > $R/echo-cluster-$J-$D.log 2>&1
      echo "echo cluster rc=$?"; cat $R/echo-cluster-$J-$D.log | cut -c1-300
      if [ "$R3OK" = 200 ]; then
        r3 timeout 1200 python $X/r8/bench_echo.py --broker $R3 --endpoint r3_site \
          --out $R/echo-r3-$J-$D.json > $R/echo-r3-$J-$D.log 2>&1
        echo "echo r3 rc=$?"; cat $R/echo-r3-$J-$D.log | cut -c1-300
      fi ;;
    publish)
      for spec in "payload 0.2" "payload 10" "payload 100" "path 10" "path 1024"; do
        set -- $spec
        f=$R/publish-cluster-$1-$2MB-$J-$D
        timeout 600 python $X/e4-hot-swap/bench_model_update.py --broker $URL --endpoint $EPN \
          --backends dragon_native --intervals 1 --seconds 20 --$1-mb $2 --path-dir $W/models \
          --out $f.json > $f.log 2>&1
        echo "publish cluster $1 $2 MB rc=$? $(grep interval $f.log | cut -c1-250)"
      done
      if [ "$R3OK" = 200 ]; then
        for mb in 0.2 10 100; do
          f=$R/publish-r3-payload-${mb}MB-$J-$D
          r3 timeout 600 python $X/e4-hot-swap/bench_model_update.py --broker $R3 --endpoint r3_site \
            --backends dragon_native --intervals 1 --seconds 20 --payload-mb $mb \
            --out $f.json > $f.log 2>&1
          echo "publish r3 payload $mb MB rc=$? $(grep interval $f.log | cut -c1-250)"
        done
      fi ;;
  esac
done
srun --overlap -N1 -n1 -w $N1 pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n $EPN" 2>/dev/null
sleep 10; kill -TERM $EP 2>/dev/null; wait $EP 2>/dev/null
srun --overlap -N1 -n1 -w $N1 dragon-cleanup > /dev/null 2>&1
kill -TERM $BP; wait $BP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
