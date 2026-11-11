# Laptop over a long link, 2026-11-11: rhapsody #139 before and after

Perlmutter was in maintenance.  Client and site endpoints on the laptop,
broker and `dt` service on radical.3 (`:8010`), about 65 ms round trip from
the laptop; one site endpoint (`r3_site`) next to the broker on radical.3.
"before": rhapsody `e66ced4` (one submit in flight per backend); "after":
rhapsody `fd3bad7` with #139 (immediate sends coalesced while one is in
flight).  DT `f46b400`, `digitaltwin` 0.1.0 on every host.

## E3 (`e3/`, `bench_sites.py`, DT service path)

Sites `lap_s0`-`lap_s2` (laptop) and `r3_site`; 50 ms of wall-clock busy
work per request; `--tasks 100 --bursts 5`; 3 repeats.  For "after", only
the broker on radical.3 was reinstalled (the backend runs in the `dt`
service).  req/s, median of bursts 2-5; placement correct at every point.

| layout, client threads | N | before | after | after / before |
|---|---|---|---|---|
| spread, c=16 | 1 | 10.9 | 28.9 | 2.65 |
| spread, c=16 | 2 | 17.5 | 40.6 | 2.33 |
| spread, c=16 | 3 | 28.4 | 45.9 | 1.62 |
| spread, c=16 | 4 | 30.4 | 56.5 | 1.86 |
| spread, c=32 | 1 | 17.1 | 36.4 | 2.13 |
| spread, c=32 | 2 | 22.2 | 52.9 | 2.38 |
| spread, c=32 | 3 | 32.5 | 64.1 | 1.97 |
| spread, c=32 | 4 | 40.3 | 77.7 | 1.93 |
| one site, c=32 | 1 | 15.9 | 38.4 | 2.42 |
| one site, c=32 | 4 | 18.9 | 35.7 | 1.89 |

After the fix one site serves more than 1/work (about 38 req/s at 50 ms):
the wall-clock busy loop lets tasks on one endpoint overlap (round 4's
open question 2).  At c=32 each request costs about 200 ms over this link,
so client threads bound the spread layout.

## E1 (`e1/`, `bench_dt_insitu.py`, client-side runtime)

Endpoint `r3_site`, each row in its own process, `--tasks 200 --bursts 5`,
3 repeats; "after" swaps rhapsody on the laptop (`PYTHONPATH`), where this
path's backend runs.  No change beyond the link's noise (c=500: bare 465
-> 468, investigator 445 -> 441, agent 441 -> 434 req/s; sequential p50
about 73 ms both).  asyncflow hands a burst of ready tasks to the backend
as one `submit_tasks` call, so E1's bursts were never limited by the
one-submit-at-a-time lock; the DT service path is, because each
`get_inference` arrives from its own client thread as its own submit.
