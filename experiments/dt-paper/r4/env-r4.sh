W=/pscratch/sd/m/merzky/dt-pm4
# Round 4 (E3): paper/dtaas f68ab66 (named engines, digitaltwin 0.1.0),
# venv ve4, harnesses from this checkout.  Sourced by r4/run_e3_*.sh.
module load cray-python/3.12.12
source $W/ve4/bin/activate
export PATH=$W/ve4/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r4-20261111
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
