# Journal: DT paper Perlmutter round 3b (2026-11-10)

Unattended Claude Code session following the round 3b page
(https://claude.ai/artifact/DyFqSmEjc4Xr9pLbgz6zKx); rules from the round 1-2c
page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn), layouts from round 3
(https://claude.ai/artifact/UKBRzfypy6hxU4TWoph9h7, `JOURNAL-pm-20261110.md`).
Branch `exp/pm-round3b-20261110` off `fca2d54` (digital.twins `paper/dtaas`).
Work dir `/pscratch/sd/m/merzky/dt-pm3`, checkout `digital.twins-r3b`, env
`$W/env5.sh` (venv `ve3b`, `D=stack-r3b-20261110`). Times PST unless marked
UTC.

## Node-hour ledger (round 3b budget: 8, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 3b`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|

## U0: setup (done, 2026-11-10 15:20)

- Started in the existing Perlmutter session (the one that ran round 3 and
  the DTaaS video work), not a fresh tmux: Andre pasted the kickoff there.
- `git clone` over SSH failed (`Permission denied (publickey)`: the ssh
  agent has no identities in this session). Decision: clone and push over
  HTTPS with `gh auth git-credential` as the credential helper (gh is
  logged in as andre-merzky); remote URL
  `https://github.com/radical-cybertools/digital.twins.git`.
- `digital.twins-r3b` at `fca2d54`, branch `exp/pm-round3b-20261110`.
  `fca2d54` has round 3's `r3/` scripts but not the follow-up ones;
  `run_t1d.sh`, `run_t2c.sh`, `run_t4c3.sh` and `t4c_merge.py` copied from
  `exp/pm-round3-20261110` (`fa440a0`) unchanged, for reference.
- `DT_PYTHON=python3.12 DT_REF=fca2d54 ./deploy/install.sh endpoint $W/ve3b`
  (cray-python 3.12.12): rc 0, "dependency sanity: OK", `pip check` clean.
  Pins: digitaltwin `fca2d54`, asyncflow `24667a5`, rhapsody-py `e66ced4`,
  radical.orbit `7904852`, ROSE `9cc47a5` (`pip freeze`); versions asyncflow
  0.6.0, rhapsody-py 0.6.0, radical.orbit 0.8.0, rose 0.3.0.
- `radical.orbit.plugin_rhapsody`: `FINISHED_RETAIN_S, TELEMETRY_RETAINED`
  = `3600.0 20000`, as the page requires. `digitaltwin` imports from the
  venv (installed, not the checkout).
- Added to the venv: py-spy 0.4.3, psutil 7.0.0.
- `s1/ledger.py 3b`: this journal's ledger (job names `r3b-*`, budget 8).
- Results under `results/r3b/<phase>/`, names as round 3 with
  `stack-r3b-20261110`.
