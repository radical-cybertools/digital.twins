W=/pscratch/sd/m/merzky/dt-pm7
# Round 7 (E2 per-session cost): paper/dtaas f4b1f16 (src/ and deploy/ as in
# c2cbc5c, so round 6's venv ve6 is reused, plus py-spy 0.4.3), harnesses
# from this checkout.  Sourced by r7/run_broker.sh.
module load cray-python/3.12.12
VE=/pscratch/sd/m/merzky/dt-pm6/ve6
source $VE/bin/activate
export PATH=$VE/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r7-20261113
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
