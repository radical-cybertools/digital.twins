# DT-as-a-Service (DTaaS) — v1 implementation plan

Status: five independent Fable review rounds (2026-08-14/15), all
findings folded in; compute-placement decision benchmarked; API model
settled: short synchronous verbs + async `twin_create` (rhapsody
pattern). Target repo:
`radical/digital_twins` (package `digitaltwin`). Related plan:
`orbit-p0-liveness-scoped-calls-plan.md` (P0) — **decoupled**: DTaaS
v1 does not depend on it; interim limitations while it is unmerged
are marked [P0-interim] below.

## 1. Goal and target semantics

Expose the experimental Digital Twin framework (this repo) as a
long-running service: an ORBIT plugin hosted on a standalone,
persistent ORBIT broker (driving use cases: AmSC / Matey fine-tuning,
xGFabric). In production the broker runs on capable dedicated
hardware. Endpoint-hosted deployment must remain possible
([P0-interim]: until P0 lands that mode sits under ORBIT's 30 s
relay backstop — harmless for the short verbs, limiting only
`get_inference`).

Agreed semantics (decisions, not open questions):

- **DTaaS is long-running; twins come and go.** Twins are defined and
  managed *programmatically* by clients (no declarative twin spec in
  v1). A serializable graph/twin description is welcome as
  introspection but must not constrain semantics.
- **n twin instances per plugin session.** A session belongs to one
  client; it hosts many independent twins. Twin teardown must not
  disturb sibling twins or the session.
- **Twins survive disappearing clients, without timeout.** Twins may
  run for days; clients attach/detach opportunistically. Sessions are
  therefore forced `persistent` server-side; reattach uses the sid as
  a bearer capability (ownership check relaxed within the
  single-token trust domain); orphans are discoverable via the admin
  listing and killable via the ordinary teardown routes. Explicit
  lifecycle only — no idle expiry.
- **Recovery of twins across broker restart is out of scope for v1**
  (candidate for v2/v3). Design state to be serializable where cheap.
- **Streams (pubsub)**: two stages. Stage 1 (v1): the DT framework's
  own ZMQ pubsub broker, run by the plugin, separate from ORBIT
  messaging. Stage 2: an ORBIT-pubsub backend behind the same
  abstraction — promoted to stretch milestone M3 for security
  reasons (risk R7), required before production. The pubsub
  abstraction is a deployment-time backend choice at the same
  architectural altitude as RHAPSODY (compute backends); the
  backend *interface* is the seam — nothing above it may depend on
  ZMQ specifics.
- **All user compute goes through the Rhapsody abstraction** (decided
  after benchmarking, §6): asyncflow engines are constructed with
  rhapsody's `OrbitExecutionBackend` targeting registered endpoints;
  a co-located endpoint (same node as the broker) is the "local"
  deployment. The broker process runs only the DT control plane. No
  in-process `ProcessPoolExecutor` for user tasks.
- **Sensors are external entities.** The graph opens at its input
  edge. A producer runs outside the framework and publishes to a
  shared channel; a twin binds that channel to an input dtype with
  `DTRuntime.add_input(dtype, channel, codec)` (M0.7). Channel topics
  carry no twin namespace, so n twins may consume one channel and the
  pubsub fan-out does the sharing. Producers precede and outlive any
  twin, and neither side manages the other. Payload codecs are a
  deployment choice: `json` for the plain scripts and instruments
  which are the normal producers, `raw` for bytes, `cloudpickle` only
  inside one trust domain (risk R7).
- **Persistent DT tasks (internal producers, in-situ loops) run in
  the plugin host process in v1** — as plain async `main_loop` code
  on the host loop, using an injected, namespaced stream client
  (M0.3). Internal producers are timers, agent loops and other
  sources a twin owns. They are no longer how data enters a graph,
  which is `add_input`.
  Persistent bodies are NOT `@flow.function_task`s: under an
  Orbit-backed engine a function task would be cloudpickled to the
  endpoint and occupy a backend slot for the twin's lifetime. This
  simplifies the user API overall (today's hand-built task wrapping
  and ZMQ clients disappear; `RuntimeAPI` gains its first publish
  path). User code on the host loop (main_loops, callbacks,
  selectors) is contractually thin async glue — documented (risk
  R2), with one cheap guard: warn at instantiation if a persistent
  component registered `function_task`s (catches the actual
  migration mistake). Remote persistent components (psij
  child-endpoint story) are post-v1.
- **Ex-situ learning uses ROSE in v1**, as a *plugin-local module*
  (the ROSE "raas" service plugin is abandoned; do not depend on it).
  ROSE's learner engine is `OrbitExecutionBackend`-backed like
  everything else, typically targeting a remote HPC endpoint. ROSE
  `StreamingActiveLearner` (PR #98, commit 64330d9) is an accepted
  dependency.
- **Trust model**: clients ship code (cloudpickle) that executes in
  the service. Accepted inside ORBIT's single-token trust domain
  (same stance as rhapsody function tasks). Per-tenant auth is
  post-v1. The DT *data plane* is currently weaker than that domain —
  see risk R7 and milestone M3.

## 2. Codebase facts the plan builds on

Verified 2026-08-14/15 against: `digital_twins` @ `main` (df3b664),
`radical.orbit` @ `devel` (8f1d18c), `rose` @
`feature/streaming_learner` (64330d9 — branch, not merged),
`rhapsody` @ dev/feature branches containing
`backends/execution/orbit.py`. Independently re-verified by four
fresh-eyes review agents.

DT framework (`src/digitaltwin`, ~1200 lines):

- `DTRuntime(flow: WorkflowEngine, streamer: PubSubClient)`
  (`runtime.py:151`) never touches ZMQ directly; the only streaming
  call is `streamer.subscribe_to_dtype` (`runtime.py:370`).
- **No `stop()`**: `start()` only sets an event; `running_tasks` are
  never cancelled; demos tear down via `flow.shutdown()` only. The
  existing done-callbacks call `.result()` before discarding
  (`runtime.py:193-197`, `runtime.py:68-72`, `components.py:209`) and
  are not cancellation-safe; component exceptions surface there as
  loop log noise, invisible to any state machine.
- **Topics are un-namespaced**: `"runtime/dtypes/<label>"`
  (`streaming.py:178`). Two twins using the same dtype label share a
  topic string and cross-subscribe — the multi-tenancy blocker,
  fixed by namespacing. (ZMQ SUBSCRIBE prefix-matching,
  `streaming.py:142`, wastes bandwidth on label-prefix overlap, but
  delivery is filtered by an exact dict lookup at `streaming.py:156`
  — the topic terminator in M0.2 is hygiene, not correctness.)
- **Transport leaks into user tasks**: every persistent task hand-
  builds `ZMQ_PS_Client("tcp://127.0.0.1:5000")` inside its
  `@flow.function_task` body (e.g.
  `test/01-start-inference-stop/sensor.py:22-32`); addresses are
  hardcoded literals repo-wide; ports fixed 5000/5001/5555.
- **Pubsub payloads are cloudpickle** on both publish and receive
  (`streaming.py:132`, `:155`) — anyone who can reach the XSUB port
  achieves code execution in every subscriber, token-free (risk R7).
- `ZMQ_Broker.run()` (`streaming.py:60-69`) is a blocking
  `zmq.proxy()` with no stop path and no random-port bind; as a
  spawn-context subprocess its stop path is terminate/join (M0.4).
- `PubSubClient.subscribe_to_dtype` silently no-ops on duplicate
  dtype (`streaming.py:196`) — per-twin clients required.
- **No stream-client teardown exists**: `ZMQ_PS_Client` has no
  `close()` (forever `_run` task `streaming.py:119`, monitor sockets
  never closed `:103-108`, per-client `zmq.asyncio.Context` never
  terminated `:84`); `PubSubClient` has no per-dtype unsubscribe.
  With per-twin clients and churning twins this leaks unboundedly —
  fixed in M0.1.
- Further latent bugs to fix in passing: un-awaited coroutine at
  `runtime.py:296`; `WindowDataType.__eq__` compares a field to
  itself (`components.py:55-60`); dead `_to_block` machinery
  (`runtime.py:177-181`).
- Existing single-session service prototype:
  `src/digitaltwin/remote/{remote_service,client}.py` (ZMQ REQ/REP;
  `package()` cloudpickles a component *class* + ctor args; service
  instantiates injecting its own `flow`, `remote_service.py:79`).
  Its README declares the ORBIT port as the intended future.
- Components take one `flow` in their constructor and register
  `@flow.function_task`s at construction — components are
  inseparable from a live engine (this binds engine lifetime to
  component lifetime: engines cannot be swapped under running twins,
  see R8).
- `pyproject.toml` declares zero dependencies (asyncflow, rhapsody,
  pyzmq, cloudpickle are actually required); `__init__.py` empty; no
  pytest suite (only runnable demos under `test/`).

ORBIT (`radical.orbit`, star topology, msgpack envelopes, 4 MiB frame
cap — the cap applies to *our control traffic* too, see M1):

- Plugin model: subclass `Plugin` with `plugin_name`,
  `session_class`, `client_class`; auto-registered at import;
  out-of-tree discovery via entry-point group `radical.orbit.plugins`
  (`plugin_host_base.py:114-129`). Broker loads with
  `--plugins default,<name>`. `is_enabled(app)` gates hosting role.
  `Plugin` already ships `unregister_session/{sid}` (no owner check,
  `plugin_base.py:600-609`) and `list_sessions` — reused, not
  duplicated, by our admin story.
- **The broker plugin host runs on a dedicated non-main thread with
  its own event loop** (`broker.py:477-488`); endpoint-hosted plugins
  likewise run on the runtime's work-loop thread. Consequence:
  radical.asyncflow 0.5.0 `WorkflowEngine.create()` **crashes there**
  (`_setup_signal_handlers` catches only `NotImplementedError`, but
  non-main threads raise `RuntimeError` from `add_signal_handler`;
  reproduced). Upstream fix is prerequisite P1. Each hosted-plugin
  call is dispatched as its own task (`broker.py:820`), so a slow
  handler does not head-of-line-block other calls.
- Sessions: per-plugin-instance state (`sid → PluginSession`), owner
  = broker-verified `x-orbit-src`; lifetime policy is chosen by the
  *client* at `register_session` (`plugin_base.py:389-429`) — a
  plugin enforces its own policy by overriding
  `_normalize_session_policy`; the owner check is overridable
  (`_check_owner`, `plugin_base.py:559`). `persistent` sessions never
  expire and are not reclaimed on owner loss. `PluginSession.close()`
  is the teardown hook; plugin-wide `shutdown()` must cancel
  background tasks.
- Call timeouts: broker-hosted (`dst='broker'`) dispatch never enters
  the broker correlation table — no broker-side deadline; the
  consumer default is 600 s, per-call overridable.
  Participant→participant relay carries a 30 s broker backstop
  removed by P0. [P0-interim]: all DTaaS verbs are short except
  `get_inference`, which defaults to a large finite wait and is the
  only endpoint-hosted casualty of the backstop.
- Eventing: `session.notify(topic, data)` → at-most-once,
  per-subscriber bounded drop-oldest queues, broker-assigned `seq`
  (gaps observable), no persistence (`replay` plugin opt-in).
- ORBIT's rhapsody plugin batches completion notifications with a
  hardcoded `NOTIFY_BATCH_WINDOW = 0.25`, flushed server-side
  (`plugin_rhapsody.py:43`, `:343`) — ~250 ms on every sequential
  task round-trip (§6). Prerequisite P2 makes it an endpoint-level
  config knob.
- TaskDispatcher is run-to-completion only; persistent remote
  processes are psij child endpoints. Not used in v1.
- No session persistence across broker restart; durable state is a
  plugin's own job (task_dispatcher's atomic-JSON `_replay_state`
  pattern is the reference).

ROSE / rhapsody:

- `StreamingActiveLearner(asyncflow, batch_size, max_wait, conflate,
  sources)`: async `feed()`, sync `attach_source()`; window =
  batch_size or
  max_wait-since-first-item; conflation bounds the queue latest-wins;
  no simulation task — stream windows are injected into training;
  criterion is a publish gate (`on_model_ready`), not a terminator;
  loop-free construction, but construct and run in the same loop;
  requires a real `WorkflowEngine` (typeguard); async-only. Exists
  only on branch `feature/streaming_learner` (64330d9) until PR #98
  merges.
- `test/rose_streaming/run_me.py` demonstrates the intended bridge:
  learner inside a `ModelInvestigator`, fed from `ON_INPUT`,
  `on_model_ready → runtime.publish_new_model`; a bootstrap model
  must be published or inference deadlocks on `has_published_model`.
  Caveat for M2: its learner tasks are shell commands with *local*
  paths (`run_me.py:44-57`) — they cannot run on a remote endpoint
  unmodified (see M2 item 11).
- rhapsody `OrbitExecutionBackend`
  (`rhapsody/backends/execution/orbit.py`): AsyncFlow-compatible
  backend over its own `EndpointRuntime`; submission batching
  (`batch_window`, hardcoded to 0 in our wiring), event-based waits,
  endpoint auto-selection, cloudpickled function tasks with a
  Python-version guard. Awaiting it can take up to `start_timeout +
  init_timeout` (30 + 120 s defaults) — this runs inside
  `twin_create`'s background initialization, never inside a held
  request. It tears down on failed init only; nothing reconnects a
  live backend if its endpoint restarts (risk R8).

## 3. Architecture

One ORBIT plugin **`dt`**, implemented in this repo as
`src/digitaltwin/service/`, registered via the
`radical.orbit.plugins` entry point. Upstream changes in v1 are
limited to prerequisites P1-P2.

- `PluginDT(Plugin)`: `plugin_name = 'dt'`, `session_class =
  DTSession`, `client_class = DTClient`, `is_enabled` unconditional
  (broker-hosted by default via `--plugins default,dt`;
  endpoint-hosted possible). Overrides `_normalize_session_policy` to
  force `lifetime='persistent'` and `_check_owner` so the sid acts as
  a bearer capability (reattach by sid). Owns the embedded DT stream
  broker: one `ZMQ_Broker` subprocess (spawn context, random or
  configured ports reported back, terminate/join stop), started on
  first need, shared by all sessions/twins, and **supervised**: a
  trivial liveness check respawns it on the same reported ports if
  it dies (clients auto-reconnect; silent stream stalls on days-long
  twins are not acceptable). **Binding policy (R7):
  loopback by default; non-loopback binds require explicit
  configuration and documented firewalling — mandatory guidance for
  any demo.**
- `DTSession(PluginSession)`: holds `twin_id → TwinInstance` and
  session-shared, `OrbitExecutionBackend`-backed engines, keyed by
  name in config: M1 creates exactly one, `'task'` (twin components;
  typically a co-located endpoint); M2 adds `'exsitu'` (ROSE
  learners; typically a remote HPC endpoint) as a non-breaking
  config addition. One engine per name per session, never per twin;
  engines initialize in `twin_create`'s background phase. Engine
  configuration: per engine name `{endpoint_name, backends}` plus
  plugin-level broker URL/token resolution; co-located-demo default
  `backends=['concurrent']` (the `dragon_v3` default would break
  demos); `batch_window` hardcoded 0. `close()` stops all twins,
  then shuts engines down — bounded by `wait_for`-wrapping
  `flow.shutdown()`, which is itself unbounded.
- **Engine selection**: none in M1 — graph verbs take no engine
  parameter; every component gets the `'task'` engine as its `flow`.
  Dual-engine injection exists only for `StreamingLearnerInvestigator`
  and is introduced with it in M2 (the class itself is the marker;
  the service detects it by subclass check). A user-facing `engine=`
  selector appears only if a non-learner component ever needs the
  remote engine. All examples/demos state their engine wiring
  explicitly.
- **API model (settled 2026-08-15, modeled on the rhapsody plugin —
  a real precedent: its `register_session` route returns the sid
  immediately and initializes in background while the *client
  helper* waits with poll fallback).** Every wire call is short:
  - `twin_create` is the one async verb: it registers the twin
    (client-supplied uuid → retry-idempotent), kicks engine
    initialization in a background task (up to ~150 s), and returns
    immediately with state `initializing`. The client helper's
    default is to poll `twin_list` until `ready`.
  - All other verbs are plain short request/response returning the
    resulting state. Graph verbs fast-fail with a clear "not ready"
    error while the twin is `initializing` — they never wait.
    No request IDs, no notifications, no verb batching (compatible
    future additions if ever needed); `twin_list` polling is the
    only observation mechanism in v1.
  - **Idempotency under reconnect** (bearer-sid retry path): `start`
    on a running twin, `stop` on a stopped twin, and `twin_close` on
    a closed twin are safe no-ops returning current state; tested in
    M1.
  - `get_inference` takes an optional client-supplied timeout
    ([P0-interim]: default large finite; post-P0: infinite) and is
    the only potentially-long call.
  - `stop` is **terminal** in v1: start-after-stop is a tested
    error; restartable twins are documented future work.
- `TwinInstance`: `DTRuntime` + its own `PubSubClient` (namespace =
  twin id; **twin ids are client-supplied uuids, globally unique
  across sessions** — the stream broker is shared plugin-wide, and
  the uuid makes `twin_create` retry-idempotent) + config + state
  machine `initializing → ready → running → stopped | failed`, with
  a last-error field fed from the done-callback exception path.
  `twin_close` on a running twin: best-effort cancel of in-flight
  backend tasks (rhapsody cancel routes), then abandon with a
  bounded timeout.
- Routes (per-session): `twin_create/{sid}`, `twin_list/{sid}`,
  `twin_close/{sid}/{twin_id}`, `twin_call/{sid}/{twin_id}` carrying
  exactly one graph verb per request (`add_input`, `add_task`,
  `add_investigator`, `add_agent`, `add_data_join`, `add_barrier`,
  `add_data_split_task`, `start`, `stop`, `describe`,
  `get_inference`; `add_input` carries a dtype, a channel string and
  a codec name, so it ships no artifact at all; `describe` returns
  the serializable graph dict —
  human-readable rendering is a client concern). A `Barrier` doesn't
  fit the `package()` class-shipping convention (post-construction
  config whose return values the client needs locally, live asyncio
  primitives), so `add_barrier` ships its spec and the service builds
  its own. One admin route: `admin/sessions` (all sessions + twins +
  owner + age + state + last error); teardown reuses the ordinary
  `twin_close`/`unregister_session` with a sid from the listing.
  Artifacts: cloudpickle-base64 in JSON, `package()` class-shipping
  carried over from `RemoteDTRuntime`, with a client-side size check
  against the 4 MiB frame cap and the client's Python + cloudpickle
  versions — the service rejects skew with a clear error.
- Client: one class, `DTClient(PluginClient)` (sync), whose public
  API *is* the `test/09-remote` shape: `get_plugin('dt') →
  create_twin() → package/add_* → start()`.
- Deployment assumption: ≥1 registered endpoint running the rhapsody
  plugin (a co-located one suffices; benchmark used
  `radical-orbit-endpoint -n <name> -p rhapsody`); Python versions
  compatible for function tasks (backend guards this).

## 4. Milestones

### P — upstream prerequisites (small PRs, first work items)

P1. **radical.asyncflow**: `WorkflowEngine` must be constructible on
    a non-main-thread event loop — catch `RuntimeError` in
    `_setup_signal_handlers` (or add `install_signal_handlers=False`);
    unit test creating an engine on a secondary-thread loop; pin the
    fixed version. Blocks M1 (both hosting modes).
P2. **radical.orbit**: the rhapsody plugin reads its notify window
    from endpoint config/env (default 0.25 unchanged; the DT `'task'`
    endpoint sets 0). One small PR in one repo; endpoint-scoped is
    the right granularity (the co-located `'task'` endpoint is
    dedicated; the `'exsitu'` endpoint keeps the default — 250 ms is
    noise under long training tasks). Blocks M1 acceptance, not M1
    development.

(P0 — liveness-scoped call correlation — is a separate, decoupled
plan; see status header.)

### M0 — framework hardening (this repo, no ORBIT)

1. `DTRuntime.stop()`: cancel `running_tasks`, stop barrier loops,
   unsubscribe topics; make
   all done-callbacks cancellation-safe AND route their exceptions
   into twin state (`failed` + last error) instead of loop log noise
   (`runtime.py:193-197`, `runtime.py:68-72`, `components.py:209`).
   Idempotent, per-twin, terminal (start-after-stop is a tested
   error), never touches shared engines. Define stop semantics for
   in-flight backend tasks: best-effort cancel, bounded abandon.
   **Stream-client teardown**: add `ZMQ_PS_Client.close()` (cancel
   `_run`, disable/close monitor sockets, term context) and
   `PubSubClient.unsubscribe_dtype()`/`close()`, wired into
   `stop()`/twin teardown. Ride-along fixes: un-awaited coroutine at
   `runtime.py:296`, `WindowDataType.__eq__` self-comparison
   (`components.py:55-60`), dead `_to_block` removal
   (`runtime.py:177-181`).
2. Topic namespacing: `PubSubClient(namespace=...)` →
   `dt/<twin_id>/dtypes/<label>`. Correctness target: identical
   dtype labels in two twins must not cross-subscribe (test exactly
   that). Also add a topic terminator (bandwidth hygiene against ZMQ
   prefix matching; not a correctness fix).
3. **Persistent-component contract**: persistent `main_loop`s run
   inline on the host loop and publish/subscribe through an
   injected, namespaced, connected `PubSubClient` exposed on
   `RuntimeAPI` — no `function_task` wrapping and no hand-built ZMQ
   clients in persistent paths; stream addresses come from config,
   not literals. (The `function_task` guard lives service-side in
   M1: only there are instantiation and `is_persistent` visible in
   one place.) Migrate all demos accordingly. (A *serializable* stream-endpoint descriptor
   is deferred until the first out-of-process stream consumer
   exists — v2 remote persistent components.)
4. `ZMQ_Broker` embedding: spawn-context subprocess launcher,
   random-port bind with bound ports reported back, loopback-default
   binding (R7), terminate/join stop. Start/stop cycling test. (No
   in-process steerable-proxy rework — the subprocess boundary is
   the stop path.)
5. Config + packaging: configurable addresses everywhere, real
   dependency list in `pyproject.toml`, package exports,
   `DTRuntime.describe() → dict` (serializable graph summary;
   introspection only; supersedes `print_graph` as the wire format).
6. Tests: pytest + tox scaffolding; unit tests for stop/teardown
   (incl. failure→`failed` state, start-after-stop error, and a
   **leak assertion**: no lingering tasks/sockets/contexts after
   twin teardown), namespacing, injected stream client; migrated
   demos.
7. **Input bindings**: `DTRuntime.add_input(dtype, channel,
   codec='json')` binds an external, shared channel to an input
   dtype. The channel topic goes on the backend verbatim, which is
   what makes it shareable, and a channel claiming the internal `dt/`
   prefix is rejected. Decoded messages enter the dtype queue exactly
   like internal traffic. Bindings are dropped by `stop()` with every
   other subscription, and `describe()` reports them. Codecs and the
   verbatim subscribe live at `PubSubClient` level, above the backend
   seam: a backend only learns that a payload is opaque bytes which it
   hands over untouched. A minimal `ChannelPublisher` keeps external
   producers to a few lines. The representative demos (01, 04) run
   their sensor as a separate process; the timer-driven demos (06, 07)
   stay as the internal-producer examples. Tested: two twins on one
   channel both receive every message.

### M1 — the ORBIT plugin (needs P1; acceptance needs P2)

7. `PluginDT` / `DTSession` / `DTClient` + routes as in §3:
   forced-persistent sessions, sid-capability reattach,
   `admin/sessions`, the API model of §3 (async `twin_create` with
   background engine init + short verbs, one verb per `twin_call`,
   idempotency semantics), `package()` size + version checks,
   embedded DT broker management (loopback-default, supervised
   respawn on same ports), the single `'task'` engine with the
   name-keyed `{endpoint_name, backends}` config schema
   (plugin-level broker URL/token; demo default
   `backends=['concurrent']`; `batch_window=0` hardcoded), and the
   service-side guard warning when a persistent component registered
   `function_task`s.
8. Port `test/09-remote` to the ORBIT client as the integration demo;
   retire `src/digitaltwin/remote/` and `test/remote_service.py`
   afterward.
9. Integration test: broker + co-located rhapsody endpoint + plugin +
   client; two concurrent twins in one session; independent teardown;
   twin churn (create/close cycles) with leak assertion; `twin_close`
   while an inference task is in flight; client disconnect → twins
   keep running → reattach by sid; idempotent retry (`twin_create`
   same uuid, `start`/`stop`/`twin_close` no-ops); component crash →
   `failed` + last error via `twin_list`. Plus one endpoint-hosted
   smoke test (create/list/close, no `get_inference`) so that mode
   doesn't silently rot. Check the §6 benchmark harness into `perf/`
   and keep it runnable against this test stack.

### M2 — ROSE ex-situ (first task: confirm PR #98 merged, else pin 64330d9)

10. `StreamingLearnerInvestigator` base class packaging the
    `rose_streaming` wiring (fed from `ON_INPUT`; `on_model_ready →
    publish_new_model`; bootstrap model handled; clean learner
    shutdown on twin stop — introduce a component stop hook here if
    task cancellation alone isn't clean, internal first). This
    milestone adds the `'exsitu'` engine (non-breaking config
    addition) and dual-engine injection: the service detects the
    class by subclass check and instantiates it with the engine set
    (learner tasks on `'exsitu'`, inference on `'task'`) — demo code
    states this explicitly.
11. Make learner tasks remote-executable: convert training/AL/
    criterion tasks to cloudpickled function tasks (version-guarded)
    or stage scripts via the ORBIT staging plugin — the
    `rose_streaming` local-path shell tasks do not survive a remote
    endpoint as-is. Integration test with distinct `'task'` and
    `'exsitu'` endpoints. Service demo (MNIST or π).

### M3 (stretch, security-motivated) — ORBIT-pubsub backend

12. `PubSubBackend` adapter over ORBIT eventing behind the M0.3
    seam: moves the DT data plane inside the token-authenticated WS
    star, eliminating the open ZMQ ports (closes R7 properly).
    Semantics fit (at-most-once, drop-oldest ≈ DT conflation); 4 MiB
    frame cap; `replay` plugin for late joiners. Required before
    production deployment; until then R7 mitigations apply.

## 5. Deferred (v2/v3)

- Moving the pubsub abstraction out of this repo to its shared
  RHAPSODY-layer home (after M3 proves the second backend); a
  serializable stream-endpoint descriptor arrives with the first
  out-of-process stream consumer.
- A channel registry. v1 has no catalogue of external channels and
  no schema for their payloads: a twin binds a channel by name and
  trusts the codec its binding names, so producer and consumer agree
  out of band. Discovery, declared payload schemas and per-channel
  policy (which codecs a deployment accepts) belong with the
  declarative twin spec.
- Per-session subprocess isolation of twin control planes (blast
  radius; §7 R2).
- **Scale-out: delegated DT hosting** — endpoint-hosted `dt` plugins
  on compute nodes, with a thin broker-side placement/registry
  front-end routing `twin_create` to a chosen endpoint and proxying
  by twin id. v1 keeps the plugin transport-agnostic precisely to
  enable this. Agreed direction (2026-08-14): stream ingress to
  compute nodes via broker-proxied streams (and/or
  outbound-subscribe backends, e.g. MQTT); twin-lifetime vs
  allocation-lifetime mismatch is an accepted limitation handled by
  endpoint deployment policies (persistent endpoints), not by twin
  migration. Revisit when approaching the centralized broker's
  performance ceiling.
- Twin recovery across broker restarts (`describe()` +
  atomic-JSON/`_replay_state` pattern makes it feasible); engine
  rebuild/self-healing after endpoint loss belongs to the same
  recovery umbrella (see R8).
- Remote persistent components (psij child endpoints); TaskDispatcher
  pool/pilot provisioning when endpoints don't pre-exist.
- Declarative twin spec; per-tenant auth (blocked on ORBIT
  per-participant identity); non-pickle data-plane wire format or
  CURVE (alternative/complement to M3 for R7); general ORBIT
  in-process participant transport for broker-hosted plugins (noted
  upstream).
- **Restartable twins** (`stop` is terminal in v1; re-arming TRUTHY
  components needs design).
- **Universal-async API mode** (verbs return request IDs, results
  via notifications): considered and rejected for v1 (2026-08-15) —
  complexity in the critical path for payoff that P0 provides
  structurally and that synchronous verbs don't need. Adding fields
  or an async mode later is a non-breaking JSON change. Verb
  batching likewise deferred until a real latency need appears.

## 6. Measured basis for the compute-placement decision

Loopback benchmark 2026-08-14 (broker + rhapsody endpoint on one
host, no-op asyncflow function task, 200 sequential calls). Exact
configuration per row — **both orbit rows ran with client-side
`batch_window=0`**; they differ only in the *server-side* notify
window (`NOTIFY_BATCH_WINDOW`, patched on the endpoint for row 3):

| path                                              | p50     | p99     | 50-concurrent  |
|---------------------------------------------------|---------|---------|----------------|
| in-process `ProcessPoolExecutor`                  | 10.9 ms | 14.1 ms |  35 tasks/s¹   |
| orbit, `batch_window=0`, notify window 0.25 s     | 261 ms  | 269 ms  | 155 tasks/s    |
| orbit, `batch_window=0`, notify window 0          | 20.2 ms | 23.2 ms | 459 tasks/s    |

¹ Anomalously below the sequential rate (~92/s); likely pool/pickle
contention under gather. Unexplained; re-measure before citing this
cell elsewhere. The placement decision does not hinge on it.

Full defaults (client batching 0.25 s *and* notify window 0.25 s)
were not measured; both delayed flushes sit on the sequential path,
so expect ~500 ms. The harness gets checked into `perf/` in M1
(item 9).

Conclusion: routing all compute through the Rhapsody abstraction
costs ~9 ms p50 per sequential in-situ prediction and *wins* under
concurrency; the 250 ms in row 2 is attributable to the server-side
notify batcher alone (hence P2 remains an M1-acceptance gate).
In-situ deadlines below ~20 ms would need in-process execution —
no current use case is near that.

## 7. Risks and dependencies

- R1 **P1 is make-or-break**: without the asyncflow fix, engine
  creation crashes in both hosting modes. First work item.
- R2 **Shared-loop blast radius**: user glue code (main_loops,
  callbacks) runs on the plugin host loop; a blocking tenant stalls
  co-hosted plugins. v1: thin-glue contract documented + production
  guidance (dedicated, adequately sized broker host — the planned
  production brokers are). v2: subprocess isolation.
- R3 **Immortal sessions leak by design**; mitigated by the
  `admin/sessions` listing (discovery) + ordinary teardown routes,
  and `twin_list` observability (incl. `failed` + last error).
- R4 Cloudpickle class-shipping over ORBIT = arbitrary code execution
  in the service, inside the single-token trust domain: documented,
  accepted for v1.
- R5 Version pins: ROSE `StreamingActiveLearner` = PR #98 / commit
  64330d9 (branch until merged); rhapsody release containing
  `OrbitExecutionBackend`; radical.orbit release containing P2;
  radical.asyncflow release containing P1.
- R6 AsyncFlow's own signal/shutdown paths must not race
  `BrokerPluginHost.shutdown()`; engine teardown in
  `DTSession.close()` is bounded by `wait_for`-wrapping
  `flow.shutdown()` — asyncflow's own shutdown is an unbounded
  gather (`workflow_manager.py:1777`), so a bare await would hang.
- R7 **Token-free RCE on the DT data plane**: pubsub payloads are
  cloudpickled; anyone reaching the XSUB port executes code in every
  subscriber — weaker than the ORBIT trust domain. v1 mitigations
  (mandatory, including for demos): loopback-default binding;
  non-loopback binds require explicit config + firewalled/private
  network, documented. Proper fix: M3 (ORBIT-pubsub backend) — and/or
  non-pickle wire format/CURVE (§5) — required before production.
- R8 **Endpoint loss strands engines**: `OrbitExecutionBackend` has
  no reconnect, and components bind their engine at construction —
  engines cannot be swapped under running twins. v1 remediation:
  documented failure mode; the session is closed (admin listing +
  `unregister_session`) and the client recreates its twins.
  Self-healing belongs to the v2/v3 recovery umbrella.
- Each milestone = one PR on a feature branch (`feature/dtaas-*`),
  tests green before stacking the next.
