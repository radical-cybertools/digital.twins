# Endpoint per thread at the ceiling (job 61292923, 256 twins, 20 Hz, 30 s)

| thread | samples | busy | busy % |
|---|---|---|---|
| orbit-work (730606) | 463 | 239 | 52% |
| dragon_native_results (730746) | 463 | 81 | 17% |
| orbit-transport (730607) | 463 | 53 | 11% |
| Thread-4 (_exq_monitor) (731161) | 463 | 18 | 4% |
| telemetry-dragon-adapter (731022) | 463 | 1 | 0% |
| dragon_native_workers (730748) | 463 | 1 | 0% |
| asyncio_0 (730745) | 463 | 1 | 0% |
| dragon_native_ops_7 (730756) | 463 | 0 | 0% |
| dragon_native_ops_6 (730755) | 463 | 0 | 0% |
| dragon_native_ops_5 (730754) | 463 | 0 | 0% |
| dragon_native_ops_4 (730753) | 463 | 0 | 0% |
| dragon_native_ops_3 (730752) | 463 | 0 | 0% |
| dragon_native_ops_2 (730751) | 463 | 0 | 0% |
| dragon_native_ops_1 (730750) | 463 | 0 | 0% |
| dragon_native_ops_0 (730749) | 463 | 0 | 0% |

## orbit-work

**tmpcd580i0t.folded**: 463 samples, 239 busy (11.9 busy thread-s, 52% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| rhapsody | 95 | 39.7% |
| telemetry | 60 | 25.1% |
| serialization | 43 | 18.0% |
| orbit | 23 | 9.6% |
| asyncio | 10 | 4.2% |
| other | 7 | 2.9% |
| websockets | 1 | 0.4% |

| inclusive (busy) | samples | share |
|---|---|---|
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 218 | 91.2% |
| `Thread._bootstrap_inner (threading.py:1075)` | 218 | 91.2% |
| `EndpointRuntime._run_work_thread (orbit/runtime.py:592)` | 218 | 91.2% |
| `Thread.run (threading.py:1012)` | 218 | 91.2% |
| `BaseEventLoop.run_forever (asyncio/base_events.py:645)` | 218 | 91.2% |
| `Thread._bootstrap (threading.py:1032)` | 218 | 91.2% |

| self (busy leaf) | samples | share |
|---|---|---|
| `Queue.put (dragon/native/queue.py:626)` | 49 | 20.5% |
| `DragonNativeExecutionBackend.submit_tasks (rhapsody/backends/execution/dragon_native.py:1630)` | 14 | 5.9% |
| `JSONEncoder.iterencode (json/encoder.py:258)` | 14 | 5.9% |
| `Pickler.dump (cloudpickle/cloudpickle.py:1313)` | 9 | 3.8% |
| `BaseTask.__contains__ (rhapsody/api/task.py:111)` | 9 | 3.8% |
| `Queue.put (dragon/native/queue.py:615)` | 7 | 2.9% |


## dragon_native_results

**tmpagoctaz8.folded**: 463 samples, 81 busy (4.0 busy thread-s, 17% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| rhapsody | 80 | 98.8% |
| asyncio | 1 | 1.2% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread._bootstrap (threading.py:1032)` | 81 | 100.0% |
| `Thread.run (threading.py:1012)` | 81 | 100.0% |
| `Thread._bootstrap_inner (threading.py:1075)` | 81 | 100.0% |
| `DragonNativeExecutionBackend._drain_results (rhapsody/backends/execution/dragon_native.py:671)` | 69 | 85.2% |
| `DragonNativeExecutionBackend._handle_messages (rhapsody/backends/execution/dragon_native.py:691)` | 67 | 82.7% |
| `Queue.get (dragon/native/queue.py:567)` | 8 | 9.9% |

| self (busy leaf) | samples | share |
|---|---|---|
| `DragonNativeExecutionBackend._handle_messages (rhapsody/backends/execution/dragon_native.py:691)` | 65 | 80.2% |
| `Queue.get (dragon/native/queue.py:567)` | 8 | 9.9% |
| `_load_value (rhapsody/backends/execution/dragon_native.py:294)` | 2 | 2.5% |
| `DragonNativeExecutionBackend._drain_results (rhapsody/backends/execution/dragon_native.py:664)` | 1 | 1.2% |
| `DragonNativeExecutionBackend._handle_messages (rhapsody/backends/execution/dragon_native.py:694)` | 1 | 1.2% |
| `DragonNativeExecutionBackend._drain_results (rhapsody/backends/execution/dragon_native.py:667)` | 1 | 1.2% |


## orbit-transport

**tmp06f6z325.folded**: 463 samples, 53 busy (2.6 busy thread-s, 11% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| asyncio | 47 | 88.7% |
| websockets | 6 | 11.3% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread.run (threading.py:1012)` | 50 | 94.3% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 50 | 94.3% |
| `EndpointRuntime._run_transport_thread (orbit/runtime.py:604)` | 50 | 94.3% |
| `Thread._bootstrap (threading.py:1032)` | 50 | 94.3% |
| `BaseEventLoop.run_forever (asyncio/base_events.py:645)` | 50 | 94.3% |
| `Thread._bootstrap_inner (threading.py:1075)` | 50 | 94.3% |

| self (busy leaf) | samples | share |
|---|---|---|
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 22 | 41.5% |
| `SSLObject.write (ssl.py:867)` | 20 | 37.7% |
| `Protocol.send_binary (websockets/protocol.py:364)` | 3 | 5.7% |
| `_SSLProtocolTransport.is_closing (asyncio/sslproto.py:104)` | 1 | 1.9% |
| `_AsyncGeneratorContextManager.__aenter__ (contextlib.py:210)` | 1 | 1.9% |
| `Connection.send_context (websockets/asyncio/connection.py:958)` | 1 | 1.9% |


## Thread-4 (_exq_monitor)

**tmpdykwlalh.folded**: 463 samples, 18 busy (0.9 busy thread-s, 4% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| other | 18 | 100.0% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread._bootstrap_inner (threading.py:1075)` | 18 | 100.0% |
| `Thread.run (threading.py:1012)` | 18 | 100.0% |
| `Thread._bootstrap (threading.py:1032)` | 18 | 100.0% |
| `ProcessGroup._exq_monitor (dragon/native/process_group.py:2209)` | 15 | 83.3% |
| `Queue.poll (dragon/native/queue.py:716)` | 12 | 66.7% |
| `ProcessGroup._exq_monitor (dragon/native/process_group.py:2208)` | 3 | 16.7% |

| self (busy leaf) | samples | share |
|---|---|---|
| `Queue.poll (dragon/native/queue.py:716)` | 11 | 61.1% |
| `ProcessGroup._exq_monitor (dragon/native/process_group.py:2208)` | 3 | 16.7% |
| `Event.is_set (threading.py:603)` | 3 | 16.7% |
| `Queue._poll (dragon/native/queue.py:487)` | 1 | 5.6% |

