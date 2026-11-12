#!/bin/bash
# start|stop a local standalone Flink cluster (1 JobManager, 1 TaskManager) on localhost, JDK 17, conf in job/conf.
set -uo pipefail
H=$(cd "$(dirname "$0")" && pwd); D=$H/../dist/flink-2.2.1
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 FLINK_CONF_DIR=$H/conf FLINK_LOG_DIR=$H/../run/log FLINK_PID_DIR=$H/../run
cd $H
case $1 in
  start) $D/bin/jobmanager.sh start; $D/bin/taskmanager.sh start
         for i in $(seq 60); do curl -sf localhost:8081/overview 2>/dev/null | grep -q '"slots-total":4' && break; sleep 0.5; done
         curl -s localhost:8081/overview; echo ;;
  stop)  $D/bin/taskmanager.sh stop-all; $D/bin/jobmanager.sh stop-all ;;
esac
