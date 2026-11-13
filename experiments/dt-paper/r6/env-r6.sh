W=/pscratch/sd/m/merzky/dt-pm6
# Round 6 (E2 broker capacity): paper/dtaas c2cbc5c (round 5 + radical.orbit
# #170), venv ve6, harnesses from this checkout.  Sourced by r6/run_broker.sh.
module load cray-python/3.12.12
source $W/ve6/bin/activate
export PATH=$W/ve6/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r6-20261113
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
