W=/global/homes/m/merzky/dt-pm5
# Round 5 on /global/homes: as r5/env-r5.sh, moved off /pscratch while some
# of its storage targets hung (2026-11-12, from about 12:00 PST).
module load cray-python/3.12.12
source $W/ve5/bin/activate
export PATH=$W/ve5/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r5-20261112
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
RT=r5
