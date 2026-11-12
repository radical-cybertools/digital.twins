W=/pscratch/sd/m/merzky/dt-pm5
# Round 5 (E3 rerun): paper/dtaas 307c247 (round 4 + rhapsody #139),
# venv ve5, harnesses from this checkout.  Sourced by r4/run_e3_*.sh.
module load cray-python/3.12.12
source $W/ve5/bin/activate
export PATH=$W/ve5/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r5-20261112
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
RT=r5
