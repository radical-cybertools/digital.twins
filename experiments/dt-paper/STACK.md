# The paper/dtaas stack

Every experiment for the DT paper from 2026-11-07 on runs on this stack, on
every host (laptop, radical.3, Perlmutter).  Each repo has a `paper/dtaas`
branch: its default branch plus the PRs below, merged as-is.  The four
dependencies are pinned by commit in `deploy/install.sh`; digitaltwin itself
is the commit that contains this file.

| Repo | Base | Merged PRs | Commit |
|---|---|---|---|
| radical.asyncflow | `main` 548b41b | #100 hot path, #110 tickless run loop, #119 + #123 cancel routing, #121, #122, #124, #126 submit-failure isolation | `cf638d955f6a75137b4fff946053d61ca92a4792` |
| rhapsody | `main` 689ded7 (has #112, #116) | #96 OrbitDataBackend, #91, #77, #123, #113 + #114 (Dragon 0.15), #125 executable stdout through ORBIT | `1937801012b69ace47f394f5a38e209d5fedaa09` |
| radical.orbit | `devel` tip (0.8.0) | none | `b10479c30bd979bcd3b5a3f4666766d054c14776` |
| ROSE | `main` (Stream API, #98) | none | `9cc47a597063351c6192e3520f1bb0d39dd35230` |
| digital.twins | `devel` f2872f8 | ROSE Stream port, orbit 0.8 session API, merge of `exp/pm-batch-20261106` | this branch |

- **Python 3.12** on every host.  The DT service compares the Python minor
  version across hosts and rejects skew; radical.3 has 3.12.3.
- **dragonhpc 0.15.0** comes with rhapsody's `[dragon]` extra; none of the
  DT harnesses need it.
- **Not merged:** asyncflow none open; rhapsody #121 (second Dragon backend),
  #103 (flux), #107 and #64 (tests only), #78 (changes requested), #90;
  orbit #156 (Dragon DDict POC); ROSE #100-#108 (UQ / spec chain);
  digital.twins #29 (superseded by the Stream port).

## What changed for the experiments

- **asyncflow's 10 ms poll is gone** (#110).  Every task paid it before; all
  E1/E2/E4 numbers measured on 0.5.1 carry about 11 ms per task that is not
  the DT.  Laptop, `bench_dt_insitu.py --workers 4`: p50 11.1 ms on 0.5.1,
  2.3 ms on this stack, with the DT rows within 0.05 ms of bare.
- **ROSE streaming is a capability of the learners**, not a separate class:
  `StreamingLearnerInvestigator` now drives `SequentialActiveLearner` with a
  `rose.Stream`.  A learner without a criterion publishes on every window
  (it used to stay on its bootstrap model).  ROSE prints per-window lines in
  stream mode; bare and DT rows pay that alike.
- **radical.orbit 0.8**: session-scoped notifications, signal forwarding,
  WebSocket compression, tests no longer write `~/.radical/orbit`.

## Update 2026-11-07

- **asyncflow #126:** a backend whose `submit_tasks` raises (a lost endpoint)
  failed the whole engine, so losing a session's learning endpoint stopped its
  in-situ inference too (round 2, R3: 4/10 and 8/10 kills through radical.3).
  Now only the refused tasks fail.
- **rhapsody #125:** executable tasks through ORBIT never completed (no stdout
  in task notifications); found in P8b.
- Round 2 numbers (`exp/pm-stack-20261107`) were measured before both; only
  R3 and executable-task runs are affected.

## Verified (laptop, 2026-11-06)

| Suite | Result |
|---|---|
| asyncflow unit / integration / stress / property | 292 / 14 / 5 / 1 passed |
| rhapsody regular / Dragon launcher | 500 passed, 9 skipped / 60 passed |
| radical.orbit unit | 2219 passed, 4 skipped; 1 timing flake (`test_ws_compression_interop[on-auto-False]`, RTT-based, passes alone) |
| ROSE unit | 301 passed |
| digital.twins unit / integration / api, full stack | 214 / 35 / 12 passed |

## Install

```sh
DT_PYTHON=python3.12 ./deploy/install.sh <broker|endpoint|client> <venv>
# exact reproduction of a recorded run: DT_REF=<digital.twins SHA> ...
```
