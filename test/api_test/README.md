# API test coverage mapping

This maps the `api_test/conftest.py` checklist of DT framework promises to the
existing numbered demos under `test/` (00-11, 100), as a starting point for
writing real pytests that check the framework does what it promises, not just
that individual functions don't crash. These are not unit tests. 

## Checklist → Demo coverage

| Checklist item | Covered by | Confidence |
|---|---|---|
| **ADD_INPUT** | 01, 04 (`runtime.add_input` binds external sensor channel) | Solid, but only via manual two-terminal run |
| **ADD_TASK - persistent** | 02, 03, 05, 06, 07, 08, 09, 10, 11 | Solid |
| **ADD_TASK - non-persistent** | Every demo's `data_sink` | Solid but incidental — nothing asserts non-persistence specifically |
| **ADD_INVESTIGATOR - input callback** | 03, 06 (gregory/nilakantha/monte_carlo), 100 | Solid |
| **ADD_INVESTIGATOR - inference task** | Nearly all demos | Solid |
| **ADD_INVESTIGATOR - inference task update** | 02, 03, 04, 05, 06, 100 (`publish_new_model`) | Solid |
| **ADD_AGENT - Model selector task** | 04, 05, 06, 09, 11, 100 | Solid |
| **ADD_AGENT - Model publish task** | 06, 100 (`model_publish_cb` override) | Solid |
| **ADD_AGENT - filter input task** | none | **Zero coverage** — `ON_FILTERED_INPUT`/`ON_FILTERED_OUTPUT` exist in runtime.py but no demo subscribes to them |
| **ADD_AGENT - inter-agent inference** | 100 only (`get_inference` chained through profiler→endpoint) | Solid but entangled with the profiler harness |
| **ADD_AGENT - Model selector update** | 04, 05, 06, 09, 11, 100 | Solid |
| **ADD_AGENT - Multi Investigators** | 05, 06, 11 | Solid |
| **ADD_BARRIER - Hard barrier** | 07 — but the hard-barrier block is **commented out** in `run_me.py` | **Effectively uncovered** |
| **ADD_BARRIER - Soft default barrier** | 07 (a/b/c soft dtypes) | Solid |
| **ADD_BARRIER - Hard(slow)/soft(fast)** | 07 mixes delays but doesn't isolate/assert this pairing | Gap |
| **ADD_BARRIER - Soft(fast)/hard(slow)** | Same — happens incidentally in 07, never asserted | Gap |
| **ADD_DATA_JOIN - Data Join** | 08 (real join), 09 (trivial single-dtype no-op join) | Solid |
| **ADD_DATA_SPLIT - task** | 09, 10 | Solid |
| **ADD_DATA_SPLIT - a None** | none — no demo's split ever returns a fully-None result | **Gap** |
| **ADD_DATA_SPLIT - one None, one Item** | 10 (`HighLow`) | Solid |
| **ADD_DATA_SPLIT - both items** | none — no split ever returns two live `TypedData` in one call | **Gap** |

## Gaps (zero real coverage today)

1. **Filter input task** (`ON_FILTERED_INPUT`/`ON_FILTERED_OUTPUT`) — mechanism exists, nothing exercises it.
2. **Hard barrier** — only example is commented out in `07-barrier/run_me.py`.
3. **Hard/soft speed-pairing semantics** — 07 runs a 5-sensor mix but never isolates or asserts either ordering.
4. **Data split → all-None result**.
5. **Data split → both outputs populated simultaneously**.

## Behaviors seen in demos but not on the checklist

- Basic lifecycle (start/stop/redeploy progression across 00→01→02)
- Shared sub-tasks across investigators (`11-shared-sim`: `register_shared_subtask`/`get_shared_subtask`/`call_shared_subtask`)
- Remote/distributed orchestration (`09-remote`: `RemoteDTOrchestrator`, `runtime.package`, `register_user_modules`)
- Resource-aware model selection (`100`) — really a richer version of "inter-agent inference"
- Windowed data reads underlying the soft barrier (`WindowDataType`/`WindowedTypeData`)
