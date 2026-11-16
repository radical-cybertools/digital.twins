#!/bin/bash
# local idle-twin run: throwaway broker + concurrent endpoint + harness
set -u
S=/home/merzky/.cache/claude-tmp/claude-1000/-home-merzky-radical-digital-twins/cbb3366c-0ab9-4060-897d-1fb21c545796/scratchpad
D=$S/idle; DT=/home/merzky/radical/paper-dtaas/digital.twins; X=$DT/experiments/dt-paper
TWINS=${1:-50,100}; TAG=${2:-smoke}; PORT=${PORT:-8471}
export PATH=$S/ve-pin/bin:$PATH PYTHONPATH=$DT/src
T=$D/tls; mkdir -p $T; chmod 700 $T
[ -f $T/broker_cert.pem ] || openssl req -x509 -newkey rsa:2048 -nodes -days 7 -subj "/CN=r8e-idle" \
   -addext "subjectAltName=IP:127.0.0.1,DNS:localhost" -keyout $T/broker_key.pem -out $T/broker_cert.pem 2>/dev/null
[ -f $T/broker.token ] || python -c "import secrets; print(secrets.token_urlsafe(32))" > $T/broker.token
chmod 600 $T/*
export RADICAL_ORBIT_BROKER_CERT=$T/broker_cert.pem RADICAL_ORBIT_BROKER_KEY=$T/broker_key.pem
export RADICAL_ORBIT_BROKER_TOKEN=$(cat $T/broker.token)
URL=https://127.0.0.1:$PORT
touch $D/orbit-stamp
RADICAL_ORBIT_BROKER_URL=wss://127.0.0.1:$PORT DT_STREAM_BACKEND=orbit RADICAL_ORBIT_LOG_FILE=$D/broker-$TAG.log \
  radical-orbit-broker.py --host 127.0.0.1 --port $PORT --plugins dt > $D/broker-$TAG.console 2>&1 &
BP=$!; sleep 8
RADICAL_ORBIT_BROKER_URL=$URL RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
RADICAL_ORBIT_LOG_FILE=$D/endpoint-$TAG.log \
  radical-orbit-endpoint.py -n idle_ep -u $URL -p default --tunnel none > $D/endpoint-$TAG.console 2>&1 &
EP=$!; sleep 10
head -c 1048576 /dev/zero > $D/model.bin
RADICAL_ORBIT_BROKER_URL=$URL python $X/r8e/bench_idle_twins.py --broker $URL --inference idle_ep --learning idle_ep \
  --broker-pid $BP --endpoint-pid $EP --twins $TWINS --model-path $D/model.bin --out $D/idle-$TAG.json
rc=$?
kill $EP $BP 2>/dev/null; sleep 3; kill -9 $EP $BP 2>/dev/null
find ~/.radical/orbit -newer $D/orbit-stamp > $D/isolation-$TAG.txt
echo "rc=$rc isolation: $(wc -l < $D/isolation-$TAG.txt) changed"
