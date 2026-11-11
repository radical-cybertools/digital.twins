# E3 Portability

Same DT on 1 to N sites, run as a service.  (Outline, 2026-10-02.)

- Baseline: xGFabric, wired by hand.
- Metrics: throughput as sites are added; code changes needed per site.

Built on named engines (digital.twins #62, paper stack `7a63751` and
later): a session's `engines` may name any engine, and a component's task
labelled `backend=<engine>` runs there.

## What is measured

`bench_sites.py`: one twin in the broker's `dt` service, a `SiteAgent`
(`e3_components.py`) with N investigators behind it.

- `--layout spread`: investigator k runs on site k.  The session
  configures `inference` on the first site's endpoint and `site_1` ...
  `site_<N-1>` on the others; the agent's package gets
  `sites=[None, "site_1", ...]`, and investigator k labels its inference
  task with `backend=sites[k]` (`None`: the default engine).
- `--layout one`: all N investigators on the first site (the reference).
- The agent round-robins requests over its investigators with a plain
  coroutine selector, so every request is exactly one task on one site.
- Each task holds the GIL for `--work-ms` (default 50 ms).  rhapsody's
  concurrent backend runs tasks in a thread pool, so one endpoint serves
  about `1000 / work_ms` requests per second (20 req/s at 50 ms), well
  below the broker's limit (E2: about 290 req/s): adding sites should add
  capacity, and putting all investigators on one site should not.
- Per N: sequential p50, then `--bursts` bursts of `--tasks` requests from
  `--concurrent` client threads; throughput is the median of bursts 2-5.
- Every answer names the endpoint its task ran on (`DT_TEST_ENDPOINT_TAG`,
  set per endpoint by the run scripts): `ran_on` and `placement_ok` in the
  JSON prove where each investigator ran.

`xgf_sites.py`: the same layout and work without the DT framework, wired
the pre-DT xGFabric way (as the `xgf` row in `e1-overhead`): one asyncflow
engine with one ORBIT backend per site, one task per site labelled with its
backend, a ZMQ request/reply service with a hand-written round-robin
dispatcher, and a ZMQ client.  Same metrics.

## Code changes per site

- DT: two lines, recorded per point in `code_per_site`: one engine config
  entry (`"site_k": {"endpoint_name": ..., "backends": [...]}`) and one
  element in the agent's `sites` list.  No wiring code: the service owns
  engines, backends, routing and the request path.
- Hand-wired: one `SITES` entry per site, plus the wiring a user owns at
  all, `wiring_lines` in the JSON: the block between the `WIRING` markers
  in `xgf_sites.py` (engine, one backend and task per site, service,
  dispatcher, client), which the DT service provides.

## Run

Perlmutter (`../r4/`):

- `run_e3_local.sh`, 5 nodes: broker with the `dt` plugin and the client on
  node 0, sites `e3_s0` ... `e3_s3` on nodes 1-4.  Throwaway TLS.
- `run_e3_remote.sh`, 4 nodes: the broker and `dt` service are radical.3's
  `:8010`; sites are three Perlmutter endpoints and `r3_site` on radical.3,
  which the laptop session starts before the job (see below).  Default
  credentials, read only.

Every host must run the same digital.twins commit, installed with
`deploy/install.sh` (client and service versions must match).

`r3_site` on radical.3 (laptop session, before the remote job):

```sh
ssh radical.3 'cd ~/paper-dtaas && tmux new-window -d -t paper-dtaas -n r3_site \
  "RADICAL_ORBIT_LOG_FILE=$HOME/paper-dtaas/logs/endpoint-r3_site.log \
   RADICAL_ORBIT_BROKER_URL=https://localhost:8010 \
   RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
   DT_TEST_ENDPOINT_TAG=r3_site \
   ve/bin/radical-orbit-endpoint.py -n r3_site -u https://localhost:8010 -p default --tunnel none"'
```

Never connect anything to radical.3's port 8011 (the E5 30-day run).

Laptop smoke test: a local broker with `--plugins dt` and three local
endpoints, as `run_e3_local.sh` does on Perlmutter, with small `--tasks`.

## Figure

`plots/make_figures.py --only e3-sites` (kept out of the default list until
`results/r4/local/` exists).
