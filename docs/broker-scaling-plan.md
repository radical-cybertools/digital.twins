# Many twins on one broker: plan (not scheduled)

Status 2026-11-16: **planned, not implemented.**  Start it if the fusion use
cases (M3D-C1, HEAT) need many *active* twins per experiment, otherwise after
the DT paper is submitted (Andre, 2026-11-16).  Most of the code is in
radical.orbit, where the SwarmSlicer work measures the same ceiling:
coordinate with it.

## Where we are

Measured on Perlmutter (DT paper rounds 8-8c, `experiments/dt-paper/`):

- One broker carries about **800-860 requests/s** in a closed loop (no-op
  tasks, 256-1,024 twins in one session).  At that ceiling no thread is
  saturated: broker event loop about 45% busy, endpoint work loop about 52%
  (round 8b B1/B3).  Cutting the broker's CPU from about 72% to 57% of a core
  (per-request log at debug, compression off) did not move it.
- A WindField twin at 1 Hz costs the broker about 8 round trips per second
  (input, inference, 16-task training bursts every 16 s, learner, model
  publishes).  One experiment holds 64 twins under 1 s p99 and breaks at 96
  (round 8c C1, with one stream participant per session, #66).
- Building a twin is cheap (about 9 ms of calls; 1,024 twins in 25 s).
  Idle twins: see "Idle cost" below.

So the limit is the **message rate** through one broker, not the number of
twins: 1,000 WindField-like twins would need about 8,000 messages/s, about
10x today.  The levers are fewer messages per twin and a cheaper path per
message.

## A finding behind lever 1

The DT service runs inside the broker process, on the plugin-host thread.
Its engines (rhapsody's `OrbitExecutionBackend`) and each session's stream
participant open an `EndpointRuntime` to the broker's own URL
(`DT_ORBIT_BROKER_URL` / `RADICAL_ORBIT_BROKER_URL`, `wss://localhost:<port>`
in our deployments; `src/digitaltwin/service/plugin.py`).  Every DT session
therefore holds loopback TLS WebSocket connections into its own process, each
with its own threads, and every task crosses that loopback twice on top of
the hop to the endpoint: msgpack encode plus TLS on one side, TLS plus parse
on the other, and thread handoffs into the router loop.  Round 8b's broker
profile fits: socket writes plus `_write_to_self` wake-ups were about 30% of
the loop's busy time.

## Shared setup

- A laptop bench: a throwaway broker with the DT plugin and a concurrent
  endpoint on loopback (as `experiments/dt-paper/r8e/` does), plus round
  8b's closed-loop client, for quick before/after numbers.
- Final numbers from one short Perlmutter round: the closed loop at 256 and
  1,024 twins (round 8b B1 / 8c C2), WindField twins per experiment (8c C1),
  and the idle run (`r8e`).  Report broker CPU per request and the ceiling.

## Lever 1: in-process path for broker-hosted plugins

Change:

1. **radical.orbit:** a `BrokerLocalRuntime` implementing the slice of
   `EndpointRuntime` that rhapsody and DT use (`start` / `stop`,
   `wait_registered`, `get_plugin` and calls, `register_callback` /
   `unregister_callback`, `send_notification`, `topology`, the frame cap)
   on the broker's routing table directly, through the broker caller and
   event tap `BrokerPluginHost` already receives (as the task dispatcher
   uses them).  Frames stay Python dicts: no msgpack, no TLS, no socket.
   One handoff per batch into the router loop, not per frame.
2. **rhapsody:** `OrbitExecutionBackend` takes an injected runtime (as
   `OrbitPubSubBackend` already does).
3. **digital.twins:** a broker-hosted `PluginDT` hands the local runtime to
   its engines and its sessions' stream participants; `DT_ORBIT_LOCAL=0`
   keeps the loopback path for comparison.

Risks: liveness and topology entries of local participants (dashboards show
`rhapsody.<sid>.<role>`), session scoping of events, backpressure (bounded
queues: a local path loses the socket's natural limit), error paths that
today come back as HTTP errors.

Expected (estimate): removes the loopback share of the broker's work and all
loopback TLS; if the ceiling with no saturated thread is handoff latency,
this is where it moves.  About 1-2 weeks across three repos, ORBIT the bulk.

## Lever 2: batch while busy

Today each task costs the broker one `task_status` frame in, each request one
response frame out; submits are already coalesced while one is in flight
(rhapsody #139); the endpoint's notification window is 0 for latency.

Change, everywhere the #139 rule (send at once when idle; while a send is in
flight or a queue is non-empty, accumulate and send all of it as one frame):

1. Endpoint `task_status` notifications (radical.orbit `plugin_rhapsody`):
   coalesce while the previous flush is in flight, instead of a fixed window.
2. The broker's per-subscriber writer: several queued events for one
   subscriber go out as one batch frame -- a protocol addition, advertised as
   a capability (like `session_events`), single frames for older peers.
3. DT stream publishes (`OrbitPubSubBackend`): coalesce per participant
   while a send is in flight (safe under the data plane's conflation rule).

Expected (estimate): frames per task from about 3 toward 1 at high load, no
added latency when idle.  About 1 week.

## Lever 3: a cheaper path per frame

1. **uvloop** for the broker, the plugin host and the runtimes: an optional
   extra (`radical.orbit[fast]`) and a switch (`RADICAL_ORBIT_LOOP=uvloop`);
   uvicorn supports it.  Check `run_coroutine_threadsafe`, the websockets
   library and Python 3.12 wheels.  Targets the top costs in round 8b's
   profile (socket writes, wake-ups).  The cheapest A/B: 1-2 days.
2. **Forward without a full parse:** for frames the broker only forwards,
   decode the envelope (destination, type) and skip pydantic validation of
   the body; optionally forward raw bytes when nothing changes (events need
   their seq / timestamp stamped, so that takes an envelope change).  Targets
   part of ORBIT's 17% for routing and protocol.  3-5 days.

## Order

1. uvloop A/B (laptop bench, then Perlmutter).
2. Lever 1 -- the largest expected gain; check it against the SwarmSlicer
   per-hop trace of the ceiling first.
3. Lever 2, when many-twin workloads (fusion) are confirmed.
4. Beyond these: a twin host next to the endpoints (an experiment's runtime
   on the HPC side, so inputs and tasks stay local and the broker carries
   client queries, control and cross-site traffic; per twin from about 8 to
   1-2 messages/s), and more than one broker process (the DT service in its
   own processes sharded by session, or a multi-process router).

## Idle cost

Measurement: `experiments/dt-paper/r8e/bench_idle_twins.py`, results in
`experiments/dt-paper/results/r8e/` (laptop, 2026-11-16; filled in below
when the run is done).
