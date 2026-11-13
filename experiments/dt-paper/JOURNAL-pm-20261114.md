# Perlmutter round 8: limit study on Dragon (started 2026-11-13 14:20 PST)

Unattended session on a Perlmutter login node, from the round 8 page
(https://claude.ai/artifact/Erj5aEKRsHjDwQmjk7e1EC). Rules: the round 1-2c
page's autonomy contract, session mechanics, ORBIT isolation and known
traps; `notes/dragon-perlmutter-pitfalls.md`. Branch `exp/pm-round8-20261114`
off `49bd91f`, merged into `paper/dtaas` at the end. Work dir
`/pscratch/sd/m/merzky/dt-pm8`. Budget 42 CPU node-h (m5290), 3 GPU node-h
(m5290_g). Ledger: `python s1/ledger.py 8`. Never radical.3 port 8011.

## Node-hour ledger (round 8 budget: 42 CPU m5290, 3 GPU m5290_g)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 8`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|

## R8-0: setup (2026-11-13 14:20 PST)

- `/pscratch` healthy: work dir `dt-pm8` there.
- `ve8`: `DT_PYTHON=python3.12 DT_REF=49bd91f94a001c944ed133efb4cf75c4f47d4841
  RHAPSODY_EXTRAS=telemetry,dragon deploy/install.sh endpoint dt-pm8/ve8`
  (cray-python 3.12.12). The pins match `STACK.md`: asyncflow `24667a5`,
  rhapsody `5abecd6`, orbit `adf2548`, ROSE `9cc47a5`, digitaltwin `49bd91f`,
  dragonhpc 0.15.0. `rhapsody.backends.execution.dragon_native` imports;
  `pip check` clean. Log `dt-pm8/logs/install-ve8.log`.
- `ve8-xgf` (GPU): round 1's TF conda env `dt-pm2/xgf/env` (Python 3.12.13,
  TF 2.21.0, numpy 2.5.0) as base, `--system-site-packages`, with the same
  pins, rhapsody `[telemetry,dragon]`, built as round 2b's `ve2b-xgf`. Log
  `dt-pm8/logs/ve8-xgf.log`.
- **Finding, backend selection:** the DT service always names its rhapsody
  backend in the remote session (`session.py`: `backends=cfg.get("backends")
  or DEFAULT_BACKENDS`, `DEFAULT_BACKENDS = ["concurrent"]`). radical.orbit
  uses the endpoint's `RADICAL_ORBIT_RHAPSODY_BACKEND` only when the client
  names none (`plugin_rhapsody._backend_names`). So
  `RADICAL_ORBIT_RHAPSODY_BACKEND=dragon_native` on an endpoint alone keeps
  DT sessions on `concurrent`. A harness must put `"backends": ["dragon_native"]`
  in each engine config (allowed: a harness change). Round 8 harnesses
  do; the endpoint also sets the variable.
- **Pool size:** `DragonNativeExecutionBackend(workers_per_node=None)` makes
  one worker per physical core of each node's `Node.cpus`. orbit's plugin
  calls `rh.get_backend(name)` with no arguments, so there is no config path
  for `workers_per_node`. R8-0 checks whether a `taskset` on the launch
  changes `Node.cpus`.
- **Launch:** each endpoint is `srun -N1 -n1 -c 256 --cpu-bind=none -w <node>
  ... dragon -s radical-orbit-endpoint.py ...`: one single-node Dragon
  runtime per endpoint, with the whole node's CPUs. Without `-c`, the step's
  CPU binding could shrink `Node.cpus`. `ulimit -n` is raised to the hard
  limit, since dragon_native warns about Local Services' descriptors.
- Harness in `r8/`:
  - `env-r8.sh`; `r8_components.py` (one investigator whose inference runs
    a function task, an executable task, or a burst of K function tasks of
    M ms CPU);
  - `smoke_dragon.py` (steps basic, gil, reattach, remote, sessions, pool);
  - `run_smoke.sh` (the R8-0 job), `wait_endpoint.py`, `node_probe.sh`
    (Dragon native processes, user processes and threads, memory);
  - `prov.py` (provenance: commits of the five packages from pip's
    `direct_url.json`, backend, workers per node, telemetry, file system);
  - round 7's `proc_sampler.sh`, `broker_table.py`, `folded_top.py`,
    `frame_counter.py` copied.
- Decision, GIL probe: the page asks that the endpoint answer "a submit and
  a twin_list within 1 s" while every pool worker runs a 10 s CPU task. A
  function-task probe would wait for a free worker, so the probe is an
  executable task (a native Process outside the pool) plus `twin_list()`.
