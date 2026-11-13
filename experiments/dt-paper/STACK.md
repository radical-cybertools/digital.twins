# The paper/dtaas stack

Every experiment for the DT paper from 2026-11-07 on runs on this stack, on
every host (laptop, radical.3, Perlmutter).  Each repo has a `paper/dtaas`
branch: its default branch plus the PRs below, merged as-is.  The four
dependencies are pinned by commit in `deploy/install.sh`; digitaltwin itself
is the commit that contains this file.

| Repo | Base | Merged PRs | Commit |
|---|---|---|---|
| radical.asyncflow | `main` 548b41b | #100 hot path, #110 tickless run loop, #119 + #123 cancel routing, #121, #122, #124, #126 submit-failure isolation, #127 slow-submit warning, #128 finished tasks released | `24667a5eae6872f9863e31ca631d8af2bc945f04` |
| rhapsody | `main` 689ded7 (has #112, #116) | #96 OrbitDataBackend, #91, #77, #123, #113 + #114 (Dragon 0.15), #125 executable stdout through ORBIT, #127 background immediate submits,  `28c8fa7cc7aa884a932316750874dbac4f056da3`| `28c8fa7cc7aa884a932316750874dbac4f056da3` |
| radical.orbit | `devel` b10479c (0.8.0) | #166 suspect-window calls failed on resume, #167 finished tasks released, #170 keepalive knob + coalesced topology | `adf25487c772791f99bf3812ea55b02bec6fc9b1` |
| ROSE | `main` (Stream API, #98) | none | `9cc47a597063351c6192e3520f1bb0d39dd35230` |
| digital.twins | `devel` f2872f8 | ROSE Stream port, orbit 0.8 session API, merge of `exp/pm-batch-20261106`, #59 cached version stamp, #60 lighter per-message path (paper-stack form, `fix/pm-message-path`) | this branch |

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
- **rhapsody #127:** with `batch_window=0` (the DT service's setting) the
  orbit backend sent each submit inline, so a submit to an endpoint the broker
  holds as suspect blocked asyncflow's run loop for the grace (~10 s): round 2b
  R3 paused in-situ inference in 17 of 30 kills. Now sent in the background.
- **asyncflow #127:** warns when a backend's `submit_tasks` holds the run loop
  > 1 s. **orbit #166:** calls to a suspect endpoint are held and answered
  with a retryable 503 on resume instead of a 504 after 30 s.

## Update 2026-11-10: finished tasks are released

The E5 long-run dry run (radical.3) grew about 60 MB/h on the inference
endpoint and 20 MB/h on the broker: every layer kept every task for the
life of a session.  asyncflow #128, rhapsody #134, orbit #167 and
digital.twins #59 release finished tasks (orbit keeps them queryable for
1 h; rhapsody telemetry is bounded when orbit asks for it).  rhapsody #134
is cherry-picked, with a follow-up for #123's waiting cancel, and a second
one that drops the finished asyncio Task from the caller's task dict (orbit's
1 h retention kept them alive; Perlmutter round 3 T1's burst decay).  The E5
30-day run started on `044ccd9`, before that second follow-up; at its task
rate the difference is about 1000 retained Tasks.

## Update 2026-11-10 (b): a lighter per-message path

digital.twins #60: a StreamingLearnerInvestigator whose in-situ answers
nobody consumes infers once per published model, not once per input; inline
ON_INPUT callbacks for the learner's feed; no gather for one component; lazy
logging.  Round 3's follow-up measured the ex-situ learner at 0.77x bare
(before 0.34x).  Other investigators are unchanged unless they opt in.

## Update 2026-11-11: named engines (E3)

digital.twins #62 (paper-stack form `feature/named-engines-stack`): a
session's `engines` may name any engine, and `engine=` on the `add_*` verbs
(or an explicit `backend=` label on a component's own task) places a
component on one.  Losing a non-default site fails only the twins placed
there; new twins that do not use it still start.  `digitaltwin` is now
0.1.0 and client and service versions must match: reinstall every host
from the same commit (`install.sh`) before an E3 run.

## Update 2026-11-12: coalesced immediate sends (rhapsody #139)

With `batch_window=0` (the DT service's setting) rhapsody's orbit backend
sent one submit at a time per backend, so a site served at most one task
per submit round trip whatever the client concurrency (round 4 W2: one
site 20 req/s at 50 ms of work).  #139 sends the tasks submitted during a
send together in the next request.  Laptop, DT service path, one site,
c=32: 17.9 -> 45.3 req/s (busy work), 71.9 -> 138.9 (asyncio.sleep).

## Update 2026-11-13: broker capacity (radical.orbit #170)

Every DT session adds a broker participant inside the broker process, and
every join or drop broadcast the full topology to all of them, so creating
sessions cost O(N^2) and at about 150 sessions the broker loop stalled past
the 3 s keepalive deadline: every connection dropped, and the reconnects
kept it there (round 3's stall at 256).  #170 coalesces topology broadcasts
(`BrokerTuning.topology_coalesce`, 0.1 s) and makes the keepalive deadline
configurable on both ends (`RADICAL_ORBIT_PING_TIMEOUT`, default 3 s, 0
disables).  Laptop: 256 sessions at 3 s (stall at 384), 384 at 20 s.

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
