# P0 — Liveness-scoped call correlation in ORBIT

Status: reviewed (Fable subagent review 2026-08-15; findings folded
in — the resulting change is *smaller* than the first sketch).
Standalone `radical.orbit` PR against `devel`. **Ordering: decoupled
from DTaaS** (2026-08-15): DTaaS v1 does not depend on P0 (see
"Ordering and DTaaS consequences" below) — implement whenever
convenient, before or after.

## Problem

A call timeout conflates two questions:

1. *Is the other side still working?* (liveness) — the only thing an
   intermediary legitimately cares about, since it must GC
   correlation state for dead parties.
2. *How long am I willing to wait?* (patience) — belongs exclusively
   to the caller; no intermediary can answer it, so any fixed cap is
   wrong for someone.

ORBIT today uses wall-clock timers for both: relayed calls carry a
hard broker backstop (`BrokerTuning.call_timeout = 30.0`,
`broker.py:110`; deadline stamped for forwarded calls at
`broker.py:838` **and** broker-originated calls at `broker.py:877`;
enforced by the `_reap_calls` sweeper, `broker.py:1114-1131`), and
the consumer side defaults to 600 s (`runtime.py:85`). Long-running
plugin verbs are legitimate; every new one restarts the
pick-a-bigger-number game.

## Design

Separate the two concerns. Review-refined; each element is the
minimal mechanism found:

- **Fail-inflight at the participant-removal chokepoint (the core
  change).** `_fail_inflight_for` exists but fires only on the
  `lost` transition (`broker.py:1061-1069`). Participants are also
  removed by *clean close* (`_on_socket_drop` with `clean=True`,
  `broker.py:1034-1038` — the common `endpoint.stop()` path) and by
  operator `_disconnect` (`broker.py:1001-1022`); both currently
  rely on the reaper. Move the `_fail_inflight_for` call into the
  `_remove_participant` chokepoint (sync context — `spawn` it) so
  all three removal paths fail in-flight calls uniformly. Then
  delete the deadline stamps, the `_reap_calls` sweeper, the
  `reap_interval` knob, and `_Call.deadline`. Caller-side cleanup on
  clean disconnect must be **added** (today it exists only in the
  lost path, `broker.py:1083-1085`).
- **No new state.** No per-participant index: `_fail_inflight_for`'s
  linear scan over `_calls` (capped at 4096, `broker.py:830-835`)
  on a rare removal event is fine. No new error machinery:
  `_fail_call` (`broker.py:1087-1101`) already synthesizes the right
  response shape — adjust the reason (e.g. `participant-lost`).
- **Suspect fast-fail.** Requests routed while the destination is
  `suspect` land on a dead socket and are silently swallowed
  (`_route_request` checks only registry presence `broker.py:823`;
  `_send` swallows failures `broker.py:1210-1216`); if the endpoint
  then *resumes* (resume keys keep `_calls` entries,
  `broker.py:744-763`), the call can never complete. Fix:
  `_route_request` fails fast with a retryable 503 when
  `liveness == 'suspect'`; treat a synchronous send failure the same
  way.
- **Consumer-side mirror: resume-key-mismatch flush.** The runtime
  keeps pending futures across reconnect (`runtime.py:524-528`) and
  silently accepts a fresh resume key from a restarted broker
  (`runtime.py:643`) whose correlation state is gone — permanent
  hangs under infinite patience. Fix: on re-register, if the
  presented resume key was not honored (fresh registration), fail
  all `_pending` futures with a connection-reset-style error.
- **Timeout knob split (client-owned patience ≠ served-handler
  bound).** `_call_timeout` is dual-use: consumer patience
  (`runtime.py:827`) *and* the served-handler bound
  (`_serve_request` wraps dispatch in `wait_for`, 504s on expiry and
  frees the admission slot, `runtime.py:735-755`). Split into two
  knobs:
  - consumer patience: **default infinity** (agreed 2026-08-15);
    per-call override unchanged; make the timeout arithmetic
    None-safe (`fut.result(timeout + 5.0)` at `runtime.py:827-833`
    crashes on `None` today).
  - served-handler bound: **stays finite** (600 s default,
    configurable). This preserves the invariant that every admitted
    request eventually gets *some* response — which is what keeps
    the broker's call table self-cleaning without the reaper (a
    black-hole endpoint would otherwise accumulate entries to the
    4096 cap and 503 all relayed calling), and frees admission
    slots under wedged handlers. Consistent with DTaaS's design:
    handlers are short by construction; long work runs in
    background tasks.
- **Call-site audit.** In-tree callers relying on defaults:
  task_dispatcher's `_CallerSyncHTTP` defaults `timeout=None`
  (`plugin_task_dispatcher.py:102`, `:117`, `:686`) — today bounded
  only by the 30 s backstop; post-change a stuck child would pin an
  `asyncio.to_thread` worker, so give these explicit timeouts.
  Gateway HTTP path keeps its own explicit 600 s
  (`gateway.py:91,590-593`) — out of scope, unchanged.
- **Residual gap, explicitly accepted:** a handler deadlocked inside
  a live process is caught by the served-handler bound, not by
  liveness. Per-request progress frames remain a possible later
  refinement, not part of P0.

Non-changes verified by review: `dst='broker'` dispatch never enters
the correlation table (`broker.py:819-821`) — unchanged; corr_ids
are uuid4 (`protocol.py:74-80`) — reuse is a non-issue.

## Tests / acceptance

New:
- Relayed call whose handler sleeps > 30 s completes with no caller
  timeout set (but under the served-handler bound).
- Serving endpoint **killed** mid-call → prompt `participant-lost`
  error (liveness window, not wall clock).
- Serving endpoint **clean-closes** (`stop()`) mid-call → same.
- Operator `disconnect` of the serving endpoint mid-call → same.
- Call issued while dst is `suspect` → fast 503; call issued
  *before* suspect completes after resume (regression: entries
  survive resume).
- Broker-originated call (`BrokerCaller` future) on endpoint death →
  future resolves with the error; thread-safe caller unblocked.
- Broker restart mid-call → consumer's pending futures fail with
  connection-reset (resume-key-mismatch flush).
- Caller-side timeout → broker call table does not grow
  monotonically (self-cleaning via served-handler bound).
- Caller disconnects mid-call → its entries dropped (both clean and
  lost paths).

Existing-suite touchpoints: `test_broker.py:667-693` (reaper test —
repurpose as "entry survives past old deadline while dst alive"),
`test_broker.py:71-72` (fixture tuning keys), `test_runtime.py:381-397`
(served-handler bound keeps honoring its knob), `test_gateway.py:403-404`
(unchanged). Re-run task_dispatcher and rhapsody-plugin integration
tests (both rely on relayed calls).

## Ordering and DTaaS consequences

DTaaS v1 does **not** depend on P0: its target deployment is
broker-hosted, and `dst='broker'` dispatch carries no broker-side
deadline today; the 600 s consumer default (per-call overridable)
covers DTaaS's slow verbs; the rhapsody backend already operates
under the 30 s relay backstop (long operations are short calls +
event waits — proven by the 2026-08-14 benchmark on vanilla ORBIT).

Until P0 lands:
- Endpoint-hosted DTaaS keeps the 30 s relay constraint (documented
  secondary-mode limitation).
- `get_inference` defaults to a large finite wait, not infinite.

After P0: those two lines are deleted from the DTaaS plan; nothing
else there changes.
