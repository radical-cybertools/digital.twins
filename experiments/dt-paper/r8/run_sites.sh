#!/bin/bash
# Round 8, R8-D: at how many sites does one twin stop scaling?
#SBATCH -J r8-d
#SBATCH -C cpu
#SBATCH -N 17
#SBATCH -t 00:50:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm8/logs/r8-d-%j.out
#   sbatch -A m5290 -q regular r8/run_sites.sh
# Node 0: broker (--plugins dt, throwaway TLS) and the client; nodes 1-16:
# one site each, an ORBIT endpoint in a single-node Dragon runtime held to
# 8 physical cores (taskset -c 0-7,128-135 -> 8 dragon_native workers, as
# R8-0 checked).  e3-portability/bench_sites.py, spread layout, work model
# cpu, 120 ms per request (FNO on CPU): one site serves about 66 req/s.
# Per N a separate run with client concurrency 16 x N (>= 2 x 8 x N in
# flight) and 120 x N requests per burst.  N = 1, 2, 4, 8, 16, REPEATS
# repeats; the hand-wired baseline (xgf_sites.py) at N = 1-4; one extra
# point N = 4 through radical.3:8010 with r3_site as one of the sites
# (STEP r3: three Perlmutter endpoints pm_r8d_s0..2 registered there, read-only
# default credentials; never port 8011).  E3_BACKENDS=dragon_native.
# Knobs: REPEATS ("1 2 3"), NS ("1 2 4 8 16"), STEPS ("dt xgf r3"), PORT (8231).
set -uo pipefail
source ${ENV_SH:-/pscratch/sd/m/merzky/dt-pm8/digital.twins/experiments/dt-paper/r8/env-r8.sh}
R=$X/results/${RES:-r8/r8-d}; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
N0=$(hostname -s)
SN=($(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$N0$"))
IP0=$(ip -4 -o addr show hsn0 | awk '{print $4}' | cut -d/ -f1 | head -1)
PORT=${PORT:-8231}
URL=https://$IP0:$PORT
R3=https://95.217.193.116:8010
E3=$X/e3-portability
SAMPLER=$PWD/$X/r8/proc_sampler.sh
export E3_BACKENDS=dragon_native R8_BACKEND=dragon_native R8_WORKERS_PER_NODE=8
echo "node0 $N0 ($IP0) sites ${#SN[@]}: ${SN[*]}  broker $URL  $(date -u +%FT%TZ)"
ulimit -Sn $(ulimit -Hn)
T=$W/tls/r8d-$J; mkdir -p $T; chmod 700 $W/tls $T
openssl req -x509 -newkey rsa:4096 -nodes -days 7 -subj "/CN=dt-pm8" \
    -addext "subjectAltName=IP:127.0.0.1,IP:$IP0,DNS:localhost,DNS:$N0" \
    -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
STAMP=$W/orbit-stamp-r8d-$J; touch $STAMP
RADICAL_ORBIT_LOG_FILE=$L/broker-r8d-$J.log RADICAL_ORBIT_BROKER_URL=$URL \
  radical-orbit-broker.py --host $IP0 --port $PORT --plugins dt > $R/broker.console-$J.log 2>&1 &
BP=$!
sleep 8
kill -0 $BP 2>/dev/null || { echo "broker died"; exit 3; }
$SAMPLER $BP > $R/broker-proc-$J-$D.txt 2>/dev/null &
SAMP=$!
export RADICAL_ORBIT_LOG_FILE=$L/client-r8d-$J.log
EPIDS=()
start_site() {  # k url name
  srun --overlap -N1 -n1 -c 256 --cpu-bind=none -w ${SN[$1]} --export=ALL \
    env RADICAL_ORBIT_LOG_FILE=$L/endpoint-r8d-$3-$J.log RADICAL_ORBIT_BROKER_URL=$2 \
        RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
        DT_TEST_ENDPOINT_TAG=$3 \
    bash -c "ulimit -Sn \$(ulimit -Hn); exec taskset -c 0-7,128-135 dragon -s $(command -v radical-orbit-endpoint.py) -n $3 -u $2 -p default --tunnel none" \
    > $R/endpoint.console-$3-$J.log 2>&1 &
  EPIDS+=($!)
}
NSITES=${#SN[@]}
for k in $(seq 0 $((NSITES - 1))); do start_site $k $URL r8d_s$k; done
for k in $(seq 0 $((NSITES - 1))); do echo "  r8d_s$k up after $(timeout 330 python $X/r8/wait_endpoint.py $URL r8d_s$k 300) s"; done
# endpoint samplers on the first two sites
for k in 0 1; do
  srun --overlap -N1 -n1 -w ${SN[$k]} $SAMPLER -f "radical-orbit-endpoint.py -n r8d_s$k" \
    > $R/endpoint-proc-r8d_s$k-$J-$D.txt 2>/dev/null &
done
EPL=$(seq -s, -f "r8d_s%g" 0 $((NSITES - 1)))
for s in ${STEPS:-dt xgf r3}; do
  for r in ${REPEATS:-1 2 3}; do
    case $s in
      dt) for n in ${NS:-1 2 4 8 16}; do
            f=$R/sites-n$n-r$r-$J-$D
            timeout ${RUN_TIMEOUT:-600} python $E3/bench_sites.py --broker $URL --endpoints $EPL --n $n \
              --layout spread --work cpu --work-ms 120 --concurrent $((16 * n)) --tasks $((120 * n)) \
              --bursts 5 --out $f.json > $f.log 2>&1
            echo "[$(date -u +%T)] dt n=$n r$r rc=$? $(grep -h 'n=' $f.log | cut -c1-220)"
          done ;;
      xgf) for n in 1 2 3 4; do
            f=$R/xgf-n$n-r$r-$J-$D
            timeout ${RUN_TIMEOUT:-600} python $E3/xgf_sites.py --broker $URL --endpoints $EPL --n $n \
              --layout spread --work cpu --work-ms 120 --concurrent $((16 * n)) --tasks $((120 * n)) \
              --bursts 5 --out $f.json > $f.log 2>&1
            echo "[$(date -u +%T)] xgf n=$n r$r rc=$? $(grep -h 'n=' $f.log | cut -c1-220)"
          done ;;
      r3) [ $r = 1 ] || continue
          code=$(curl -sk -o /dev/null -m 10 -w '%{http_code}' $R3/); echo "radical.3:8010 http $code"
          [ "$code" = 200 ] || continue
          # one Dragon runtime per node: stop the local sites r8d_s0..2 first
          # (r3 is the last step; dt and xgf are done)
          for k in 0 1 2; do srun --overlap -N1 -n1 -w ${SN[$k]} pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n r8d_s$k" 2>/dev/null; done
          sleep 10
          for k in 0 1 2; do srun --overlap -N1 -n1 -w ${SN[$k]} dragon-cleanup > /dev/null 2>&1; done
          ( unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
            for k in 0 1 2; do start_site $k $R3 pm_r8d_s$k; done
            for k in 0 1 2; do echo "  pm_r8d_s$k up after $(timeout 200 python $X/r8/wait_endpoint.py $R3 pm_r8d_s$k 180) s"; done
            export RADICAL_ORBIT_LOG_FILE=$L/client-r8d-r3-$J.log
            for rr in 1 2 3; do
              f=$R/sites-r3-n4-r$rr-$J-$D
              timeout 600 python $E3/bench_sites.py --broker $R3 --endpoints pm_r8d_s0,pm_r8d_s1,pm_r8d_s2,r3_site \
                --n 4 --layout spread --work cpu --work-ms 120 --concurrent 64 --tasks 480 --bursts 5 \
                --out $f.json > $f.log 2>&1
              echo "[$(date -u +%T)] r3 n=4 r$rr rc=$? $(grep -h 'n=' $f.log | cut -c1-260)"
            done
            for k in 0 1 2; do srun --overlap -N1 -n1 -w ${SN[$k]} pkill -TERM -u $USER -f "radical-orbit-endpoint.py -n pm_r8d_s$k" 2>/dev/null; done ) ;;
    esac
  done
done
ps=(); for k in $(seq 0 $((NSITES - 1))); do srun --overlap -N1 -n1 -w ${SN[$k]} pkill -TERM -u $USER -f "radical-orbit-endpoint.py" 2>/dev/null & ps+=($!); done; wait ${ps[@]}
sleep 10; kill -TERM ${EPIDS[@]} 2>/dev/null; wait ${EPIDS[@]} 2>/dev/null
ps=(); for k in $(seq 0 $((NSITES - 1))); do srun --overlap -N1 -n1 -w ${SN[$k]} dragon-cleanup > /dev/null 2>&1 & ps+=($!); done; wait ${ps[@]}
kill $SAMP 2>/dev/null
kill -TERM $BP; wait $BP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $STAMP | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end $(date -u +%FT%TZ)"
