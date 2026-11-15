W=/pscratch/sd/m/merzky/dt-pm8
# Round 8c (converge on the default stack): paper/dtaas a64effc (round 8b's
# 63d8692 plus #65, a step's own timeout keeps its message, and #66, one ORBIT
# stream participant per DT session), venv ve8c (install.sh,
# RHAPSODY_EXTRAS=telemetry,dragon), harnesses from this checkout.  Sourced by
# the r8/*.sh and r8b/*.sh runners through ENV_SH.  Knobs:
#   VE                            venv (default ve8c)
#   RADICAL_ORBIT_WS_COMPRESSION  unset = orbit's default (auto: deflate off
#       inside the cluster, as in rounds 8 and 8b); set it to override.
module load cray-python/3.12.12
VE=${VE:-$W/ve8c}
source $VE/bin/activate
export PATH=$VE/bin:$PATH
cd $W/digital.twins
X=experiments/dt-paper
D=stack-r8c-20261115
# Compression: orbit default (auto; deflate off inside the cluster) unless the caller sets it
[ -n "${RADICAL_ORBIT_WS_COMPRESSION:-}" ] && export RADICAL_ORBIT_WS_COMPRESSION
export R8_VENV=$VE
export PIP_CACHE_DIR=$W/cache/pip
mkdir -p $W/orbit-logs $W/tls $W/logs
