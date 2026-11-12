#!/bin/bash
# Build job-v1.jar and job-v2.jar (same job, different Model class) with JDK 17 against Flink's lib jars.
set -euo pipefail
H=$(cd "$(dirname "$0")" && pwd); D=$H/../dist/flink-2.2.1
J=/usr/lib/jvm/java-17-openjdk-amd64/bin
CP=$(ls $D/lib/*.jar | tr '\n' :)
for v in 1 2; do
  rm -rf $H/build/v$v; mkdir -p $H/build/v$v
  $J/javac --release 17 -nowarn -cp "$CP" -d $H/build/v$v $H/src/common/e4/*.java $H/src/v$v/e4/Model.java
  $J/jar --create --file $H/job-v$v.jar -C $H/build/v$v .
done
ls -la $H/job-v*.jar
