W=/pscratch/sd/m/merzky/dt-pm8
# Round 8b (broker cost): paper/dtaas a3e64c7 (round 8's fdf9a5b plus #63,
# 'Online run' at debug level), venv ve8b (install.sh, RHAPSODY_EXTRAS=
# telemetry,dragon), harnesses from this checkout.  Sourced by the r8/*.sh
# runners through ENV_SH.  Knobs:
#   VE                            venv (default ve8b; B1 also runs round 8's ve8)
#   RADICAL_ORBIT_WS_COMPRESSION  on / off / auto (default off).  Note: orbit's
#       default is auto, which in round 8 chose 'deflate off' on every
#       in-cluster connection (connect 0.4-0.6 ms < 10 ms threshold), so
#       'on' here is the counterfactual, not round 8's setting.
module load cray-python/3.12.12
VE=${VE:-$W/ve8b}
source $VE/bin/activate
export PATH=$VE/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r8b-20261114
export RADICAL_ORBIT_WS_COMPRESSION=${RADICAL_ORBIT_WS_COMPRESSION:-off}
export R8_VENV=$VE
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
