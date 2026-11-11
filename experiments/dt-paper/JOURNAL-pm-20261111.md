# Journal: DT paper Perlmutter round 3c (2026-11-11)

Unattended Claude Code session following the "Round 3c" section of the round
3b page (https://claude.ai/artifact/DyFqSmEjc4Xr9pLbgz6zKx); rules from the
round 1-2c page (https://claude.ai/artifact/UNbNDCc2cRocjXqrTKXHKn). Branch
`exp/pm-round3c-20261111` off `e660bb9` (round 3b's branch, on
`paper/dtaas` `fca2d54`). Work dir `/pscratch/sd/m/merzky/dt-pm3`, checkout
`digital.twins-r3b` (new branch in it), env `$W/env6.sh` (venv `ve3b`,
`D=stack-r3c-20261111`). Round 3b: `JOURNAL-pm-20261110b.md`. Times PST
unless marked UTC.

## Node-hour ledger (round 3c budget: 1.5, CPU, m5290)

Updated after every job (sacct elapsed x nodes), `python s1/ledger.py 3c`.

| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |
|---|---|---|---|---|---|---|---|
| 61137684 | r3c-v12 | m5290 | 1 | 00:10:30 | 0.175 | 0.17 | 0.00 |
| 61137685 | r3c-v3 | m5290 | 2 | 00:12:04 | 0.402 | 0.58 | 0.00 |
| 61138155 | r3c-v4 | m5290 | 2 | 00:12:22 | 0.412 | 0.99 | 0.00 |

## Setup (2026-11-11 00:20)

- Same Perlmutter session as round 3b. GitHub over SSH again (the key Andre
  added sits in another agent socket; this shell points `SSH_AUTH_SOCK` at
  it). `memo sync`: up to date.
- `ve3b` reused (still at `fca2d54`, unchanged since round 3b).
- Harness changes, all opt-in, defaults unchanged:
  - `r3b/nogc.py --gc-threshold G0[,G1[,G2]]` (V2); `--freeze` now calls
    `gc.freeze()` (round 3b's only printed it; never used in a run).
  - `bench_dt_insitu.py` provenance records `gc_enabled` and
    `gc_threshold` of the client process.
  - `s1/ledger.py 3c`: this journal's ledger.
- Scripts: `r3c/run_v12.sh` (V1 and V2 in one 1-node job, so V2 compares
  with V1 on the same node), `r3c/run_v3.sh` (2 nodes), V4 is
  `s2/run_s2.sh PARTS=r1 CS=1`.
- Decisions: V2 threshold `100000,50,50` (the section's example). V3 runs
  rows bare, investigator and agent (not xgf: the slow first bursts hit
  every row, and 4 rows x 10 x 4 settings would not fit the 0.5 node-h
  guide); rows rotated per repeat; a fresh endpoint per setting.

## V1: pool sweep, five bursts per row (done, 2026-11-11 00:26)

Job 61137684 (r3c-v12, debug, 1 node, 10:27, V1 and V2;
`r3c/run_v12.sh`, `results/r3c/v1/`). 90 runs, every rc 0; provenance
`97c3791`, client GC `(700, 10, 10)` (the default). Tables:
`results/r3c/v12-table-stack-r3c-20261111.md` (`r3c/v12_table.py`),
`results/r3c/v1/compare-u4-vs-v1.md` (round 3b U4 P1, one burst, vs this;
its req/s column is the first burst).

- Bursts 2-5, x bare: c=50 0.91-1.02 (investigator 0.93-1.02, agent
  0.91-1.02); c=500 investigator 0.91-0.98, agent 0.85-0.93. Seq p50 within
  0.12 ms of bare at every pool (0.53-1.43 ms), as in U4.
- First burst at c=500: now the investigator loses (0.70-0.79x at pools
  1-128, 0.95 at 256), the agent is 0.88-1.02x. With five bursts per row the
  collections fall elsewhere than in U4's single-burst runs (agent lost
  there), as U4b/U4c predict.
- For the figure: bursts 2-5 (median), per the section.

## V2: raised GC threshold (done, 2026-11-11 00:26)

Same job, after V1 on the same node (`results/r3c/v2/`), 15 runs, every rc
0, client GC threshold `(100000, 50, 50)` in every JSON's provenance.

| pool | row | V1 first | V2 first | V1 bursts 2-5 | V2 bursts 2-5 | V2 bursts 2-5 x bare |
|---|---|---|---|---|---|---|
| 1 | bare | 3516 | 2958 | 3573 | 3709 | 1.00 |
| 1 | investigator | 2754 | 3503 | 3400 | 3586 | 0.97 |
| 1 | agent | 3399 | 3566 | 3195 | 3539 | 0.95 |
| 8 | bare | 3718 | 3182 | 3783 | 3914 | 1.00 |
| 8 | investigator | 2785 | 3512 | 3547 | 3694 | 0.94 |
| 8 | agent | 3452 | 3555 | 3309 | 3679 | 0.94 |
| 64 | bare | 2827 | 2539 | 2890 | 3009 | 1.00 |
| 64 | investigator | 2229 | 2938 | 2752 | 2954 | 0.98 |
| 64 | agent | 2857 | 2544 | 2688 | 3022 | 1.00 |

- Bursts 2-5 rise 3-11% for every row (bare +3-4%, investigator +4-7%,
  agent +11-12%); the DT rows come to 0.94-1.00x bare.
- First bursts: the DT rows' first bursts come up to their bursts 2-5
  (investigator 2754 -> 3503 at pool 1), except the agent at pool 64. Bare's
  first burst drops instead (3516 -> 2958 at pool 1, 0.84-0.90x of V1) in
  every repeat (2792-3285 at pools 1 and 8): with collections rarer, the
  first one is larger and falls in the first burst of the run.
- Reading against the section's test: bursts 2-5 do not match V1 exactly
  (3-12% higher), and the first bursts come up for the DT rows, not for bare.
  So the collector explains the single-burst variance, and it also costs
  3-12% on bursts 2-5 at its default threshold, more for the DT rows (which
  allocate more per request). Decision: report both as the finding; no
  further runs (the section asks for this check only).

## V3: the rare slow first burst through ORBIT (done, 2026-11-11 00:28)

Job 61137685 (r3c-v3, debug, 2 nodes; `r3c/run_v3.sh`, `results/r3c/v3/`).
U2's cross-node layout, c=50, rows bare / investigator / agent each in its
own process, 10 repeats per row, 5 bursts each, four settings, a fresh
endpoint per setting. 120 runs, every rc 0; isolation check empty. Client
GC state in each JSON's provenance (`gc_enabled`); the endpoint's console
log shows `nogc: gc disabled` for both endpoint-off settings. Table
`v3-count-stack-r3c-20261111.md` (`r3c/v3_count.py`).

| client GC | endpoint GC | first bursts < 600 req/s | which | all bursts < 600 | bursts 2-5 median |
|---|---|---|---|---|---|
| on | on | 2 of 30 | bare r1 381, investigator r6 406 | 6 of 150 | 1014 |
| off | on | 2 of 30 | bare r1 387, investigator r6 464 | 7 of 150 | 1038 |
| on | off | 1 of 30 | bare r2 476 | 1 of 150 | 1030 |
| off | off | 0 of 30 | - | 0 of 150 | 1026 |

- Turning the client's collector off changes nothing (2 / 6 -> 2 / 7).
  Turning the endpoint's off removes them (2 / 6 -> 1 / 1, and 0 / 0 with
  both off). With the endpoint's GC on, the slow first bursts land on the
  same runs in both settings (bare r1, investigator r6): the same point in a
  fresh endpoint's lifetime, as collections at fixed allocation counts would.
- Finding: the rare slow burst is the endpoint process's cyclic garbage
  collector. Counts are small (30 first bursts per setting), so this is a
  consistent pattern, not a statistical test; per the section, no further
  digging.
- Bursts 2-5 median 1014-1038 req/s in every setting (U2 solo c=50: 1010).

## V4: c=1 through radical.3 again (done, 2026-11-11 00:55)

Job 61138155 (r3c-v4, debug, 2 nodes, 12:22), `s2/run_s2.sh PARTS=r1 CS=1
KS="1 2 3 4 5"`, `--tasks 100`, endpoint `pm_e1_ep_61138155` on node A,
client on node B, broker `https://95.217.193.116:8010`, default
credentials (read only). Every rc 0; isolation check empty.
`results/r3c/v4/`, tables `r1-compare-u3-vs-v4.md`, `r1-compare-c3-vs-v4.md`.

| row | 2c p50 ms | U3 p50 ms | V4 p50 ms (repeats) |
|---|---|---|---|
| bare | 347.82 | 353.91 | 353.00 (346.77-353.74) |
| investigator | 347.84 | 353.98 | 353.09 (346.67-353.54) |
| agent | 348.02 | 353.85 | 353.18 (346.67-353.52) |

- V4 reproduces U3 (-0.7 to -0.9 ms). One repeat (r1, 346.8 ms) sits at
  2c's level, the other four at 351.7-353.7: the per-repeat level moves by
  about 6 ms between runs, for every row alike. WAN connect p50 172 ms
  (165-180), as in U3 and 2c.
- DT rows within 0.2 ms of bare. Finding: the c=1 offset against 2c is the
  WAN path to radical.3, which varies by about 6 ms between runs; not the
  stack.

## Close-out (round 3c, 2026-11-11 01:00)

| phase | status | headline |
|---|---|---|
| V1 | done | pool sweep, 5 bursts per row: DT rows 0.91-1.02x bare at c=50 and 0.85-0.98x at c=500 on bursts 2-5; the single-burst loss moved to the investigator's first burst (0.70-0.79x) |
| V2 | done | client GC threshold (100000, 50, 50): DT rows' first bursts come up, bare's first burst drops (one larger collection); bursts 2-5 +3-12%, DT rows 0.94-1.00x bare |
| V3 | done | rare slow ORBIT burst = the endpoint's cyclic GC: 6-7 of 150 slow bursts with it on, 0-1 with it off; client GC makes no difference |
| V4 | done | c=1 via radical.3 353.0 ms (U3 353.9, 2c 347.8); one repeat at 2c's level; WAN path variance |

Node-hours: 0.99 of 1.5 (m5290; ledger above). No allocation left running.
Every ORBIT job's isolation check is empty (v3, v4). No `src/` change, no
fix branch. Harness changes: `r3b/nogc.py --gc-threshold` (and a working
`--freeze`), GC state in `bench_dt_insitu.py` provenance, `s1/ledger.py 3c`,
new `r3c/` scripts and tables. Provenance commits in the JSONs: 97c3791
(219), 1b03cbc / 41e1681 / 0124c0b (11; I committed results while V3/V4
ran); none of those commits touches the harnesses or `src/`
(`git diff --stat 97c3791 HEAD -- e1-overhead src r3b/nogc.py` is empty).
Branch `exp/pm-round3c-20261111` pushed; no PR.

Open questions for Andre:

1. V2: at the default GC threshold the collector costs 3-12% on bursts 2-5
   (more for the DT rows). Should the paper say so next to the e1-pool
   figure (V1, default GC), or only the one sentence about single-burst
   variance?
2. V3: the endpoint's collector causes the rare slow ORBIT burst. Worth a
   note for the endpoint (e.g. `gc.freeze()` after start-up, or a raised
   threshold), or just a sentence in the paper?
3. Round 3b's merge into `paper/dtaas` (Andre's answer 5): this branch
   holds round 3b's commits up to `e660bb9` plus round 3c; merge this one
   instead? Round 3b's branch has one more journal-only commit after
   `e660bb9` (`8d10e6f`: Andre's answers, the Q3 code check) not in this
   one.
