W=/pscratch/sd/m/merzky/dt-pm8
# Round 8 (limit study on Dragon): paper/dtaas 49bd91f (rhapsody 5abecd6 with #147
# and #121 dragon_native), venv ve8 (install.sh, RHAPSODY_EXTRAS=telemetry,dragon),
# harnesses from this checkout.  Sourced by r8/*.sh.
module load cray-python/3.12.12
VE=$W/ve8
source $VE/bin/activate
export PATH=$VE/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r8-20261114
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
