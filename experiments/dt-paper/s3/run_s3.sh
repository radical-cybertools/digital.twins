#!/bin/bash
#SBATCH -J s3-service
#SBATCH -C cpu
#SBATCH -N 2
#SBATCH -t 00:20:00
#SBATCH -o /pscratch/sd/m/merzky/dt-pm3/logs/s3-%j.out
# Round 2 S3 (stretch, preliminary): a twin in the radical.3 broker's dt
# service, its engine on a Perlmutter endpoint (node A), the client on node
# B.  Credentials and isolation as in S2 (run_s2.sh).
#   sbatch -A m5290 -q debug run_s3.sh
set -uo pipefail
source /pscratch/sd/m/merzky/dt-pm3/env.sh
unset RADICAL_ORBIT_BROKER_CERT RADICAL_ORBIT_BROKER_KEY RADICAL_ORBIT_BROKER_TOKEN
export RADICAL_ORBIT_BROKER_URL=https://95.217.193.116:8010
URL=$RADICAL_ORBIT_BROKER_URL
R=$X/results/s3; mkdir -p $R
L=$W/orbit-logs
J=$SLURM_JOB_ID
NA=$(hostname -s)
NB=$(scontrol show hostnames $SLURM_JOB_NODELIST | grep -v "^$NA$" | head -1)
echo "node A $NA (endpoint)  node B $NB (client)  broker $URL"
touch $W/orbit-stamp-s3-$J
for i in $(seq 20); do
  curl -sk -o /dev/null -m 10 -w '%{http_code} %{time_connect}\n' $URL/
done > $R/wan-rtt-nodeA-$J-$D.txt
echo "WAN connect p50 $(cut -d' ' -f2 $R/wan-rtt-nodeA-$J-$D.txt | sort -n | sed -n 10p) s," \
     "http $(cut -d' ' -f1 $R/wan-rtt-nodeA-$J-$D.txt | sort | uniq -c | tr '\n' ' ')"

EP=pm_s3_ep_$J
RADICAL_ORBIT_LOG_FILE=$L/s3-endpoint-$EP.log \
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
DT_TEST_ENDPOINT_TAG=$EP \
  radical-orbit-endpoint.py -n $EP -u $URL -p default --tunnel none \
  > $R/endpoint-$EP.console.log 2>&1 &
EPP=$!
sleep 20
kill -0 $EPP || { echo "endpoint died"; tail -5 $R/endpoint-$EP.console.log; }

RADICAL_ORBIT_LOG_FILE=$L/s3-client.log \
  srun --overlap -N1 -n1 -w $NB --export=ALL \
  python $X/s3/s3_service.py --broker $URL --inference $EP --n 100 --repeats 3 \
  --reattaches 10 --out $R/service-remote-$D.json > $R/service-remote-$D.log 2>&1
echo "S3 rc=$?"; grep -E "^repeat|^reattach|FAILED|^\{" $R/service-remote-$D.log

kill -TERM $EPP 2>/dev/null
for i in $(seq 15); do kill -0 $EPP 2>/dev/null || break; sleep 1; done
kill -KILL $EPP 2>/dev/null
echo "--- ~/.radical/orbit newer than stamp (must be empty):"
find ~/.radical/orbit -newer $W/orbit-stamp-s3-$J | tee $R/orbit-isolation-check-$J-$D.txt
echo "--- end"
