#!/bin/bash
#SBATCH -J s2-remote
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:30:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/s2-%j.out
# Round 2 S2: runs through the shared paper/dtaas broker on radical.3.
#   sbatch -A m5290 -q debug --export=ALL,PARTS=r1,KS="1 2 3" run_s2.sh
#   PARTS: any of r1 r2 r4 r3 (default all); KS: R1 repeats (default 1-5).
#   The WAN RTT is measured in every job (once per allocation).
# Node A (the batch node) hosts the endpoints, node B the clients.  The
# broker is shared: never restarted, every endpoint named pm_*_<jobid>.
# Credentials: the ~/.radical/orbit defaults (read only; the page allows
# reading broker_cert.pem and broker.token for S2), so no
# RADICAL_ORBIT_BROKER_{CERT,KEY,TOKEN} is set.  Every process logs to
# its own RADICAL_ORBIT_LOG_FILE; ~/.radical/orbit is checked around it all.
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm3/env.sh
unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
export RADICAL_ORBIT_BROKER_URL=https://95.217.193.116:8010
URL=$RADICAL_ORBIT_BROKER_URL
R=$X/results/s2; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
NA=$(hostname -s)
NB=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$NA$" | head -1)
echo "node A $NA (endpoints)  node B $NB (clients)  broker $URL"
touch $W/orbit-stamp-s2-$J

onB() { srun --overlap -N1 -n1 -w $NB --export=ALL "$@"; }

# --- reachability and WAN RTT, from both nodes
rtt() {  # label
  for i in $(seq 20); do
    curl -sk -o /dev/null -m 10 -w '%{http_code} %{time_connect}\n' $URL/
  done > $R/wan-rtt-$1-$D.txt
  echo "$1: http $(cut -d' ' -f1 $R/wan-rtt-$1-$J-$D.txt | sort | uniq -c | tr '\n' ' ')" \
       "connect p50 $(cut -d' ' -f2 $R/wan-rtt-$1-$J-$D.txt | sort -n | sed -n 10p) s"
}
rtt nodeA
export -f rtt; export R D URL J
onB bash -c 'rtt nodeB'
grep -q "^200 " $R/wan-rtt-nodeA-$J-$D.txt && grep -q "^200 " $R/wan-rtt-nodeB-$J-$D.txt || {
  echo "compute nodes cannot reach the broker: skipping S2 compute-node runs"
  find ~/.radical/orbit -newer $W/orbit-stamp-s2-$J | tee $R/orbit-isolation-check-$J-$D.txt
  exit 6; }

start_ep() {  # name -> EP pid (on node A, this node)
  RADICAL_ORBIT_LOG_FILE=$L/s2-endpoint-$1.log \
  RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
  DT_TEST_ENDPOINT_TAG=$1 \
    radical-orbit-endpoint.py -n $1 -u $URL -p default --tunnel none \
    > $R/endpoint-$1.console.log 2>&1 &
  EP=$!
  sleep 20
  kill -0 $EP || { echo "endpoint $1 died"; tail -5 $R/endpoint-$1.console.log; }
}
stop() {
  kill -TERM $1 2>/dev/null
  for i in $(seq 15); do kill -0 $1 2>/dev/null || return 0; sleep 1; done
  kill -KILL $1 2>/dev/null
}

PARTS=${PARTS:-r1 r2 r4 r3}
has() { case " $PARTS " in *" $1 "*) return 0;; esac; return 1; }

# --- R1 / R2 / R4: one endpoint on A, clients on B
if has r1 || has r2 || has r4; then
E1=pm_e1_ep_$J
start_ep $E1
has r1 && for k in ${KS:-1 2 3 4 5}; do
  for c in 1 50 500; do
    f=$R/insitu-pm-remote-c$c-r$k-$D
    RADICAL_ORBIT_LOG_FILE=$L/s2-client-r1.log onB \
      python $X/e1-overhead/bench_dt_insitu.py --broker $URL --endpoint $E1 \
      --tasks ${TASKS:-100} --concurrent $c --out $f.json > $f.log 2>&1
    echo "R1 c$c r$k rc=$? $(grep -h -E 'p50|req/s' $f.log | sed 's/  */ /g' | tr '\n' '|' | cut -c1-260)"
  done
done
if has r2; then
RADICAL_ORBIT_LOG_FILE=$L/s2-client-r2.log onB \
  python $X/e1-overhead/bench_streams.py both --broker $URL > $R/streams-remote-$D.log 2>&1
echo "R2 rc=$?"; grep -h -E "p50|msg/s" $R/streams-remote-$D.log | sed 's/  */ /g'
fi
has r4 && for k in 1 2 3; do
  f=$R/update-pm-remote-r$k-$D
  RADICAL_ORBIT_LOG_FILE=$L/s2-client-r4.log onB \
    python $X/e4-hot-swap/bench_model_update.py --broker $URL --endpoint $E1 \
    --intervals 1,0.1 --seconds 20 --out $f.json > $f.log 2>&1
  echo "R4 r$k rc=$?"; grep -h interval $f.log
done
stop $EP
fi

# --- R3: E5 through the broker's dt service.  Inference endpoint on B;
# bench_endpoint_loss.py runs on A and owns the learning endpoint there.
if has r3; then
EI=pm_p6_inf_$J
RADICAL_ORBIT_LOG_FILE=$L/s2-endpoint-$EI.log \
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
DT_TEST_ENDPOINT_TAG=$EI \
  srun --overlap -N1 -n1 -w $NB --export=ALL \
  radical-orbit-endpoint.py -n $EI -u $URL -p default --tunnel none \
  > $R/endpoint-$EI.console.log 2>&1 &
EPI=$!
sleep 25
RADICAL_ORBIT_LOG_FILE=$L/s2-client-r3.log \
  python $X/e5-persistence/bench_endpoint_loss.py --broker $URL --inference $EI \
  --learning pm_p6_learn_$J --kills ${KILLS:-10} --reattaches ${REATTACHES:-10} \
  --logs $L --out $R/endpoint-loss-remote-$D.json > $R/endpoint-loss-remote-$D.log 2>&1
echo "R3 rc=$?"; grep -E "^kill|^reattach|FAILED" $R/endpoint-loss-remote-$D.log
stop $EPI
fi

echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $W/orbit-stamp-s2-$J | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end"
