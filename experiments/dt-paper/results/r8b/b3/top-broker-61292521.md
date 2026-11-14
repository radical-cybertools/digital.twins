**pyspy-profiled-61292521-broker.folded**: 16544 samples, 755 busy (37.8 busy thread-s, 5% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| other | 490 | 64.9% |
| asyncio | 153 | 20.3% |
| orbit | 47 | 6.2% |
| serialization | 16 | 2.1% |
| dt service | 16 | 2.1% |
| websockets | 14 | 1.9% |
| asyncflow | 12 | 1.6% |
| rhapsody | 7 | 0.9% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread.run (threading.py:1012)` | 598 | 79.2% |
| `Thread._bootstrap (threading.py:1032)` | 598 | 79.2% |
| `Thread._bootstrap_inner (threading.py:1075)` | 598 | 79.2% |
| `_dump (frame_counter.py:79)` | 484 | 64.1% |
| `BaseEventLoop.run_forever (asyncio/base_events.py:645)` | 186 | 24.6% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 183 | 24.2% |
| `Handle._run (asyncio/events.py:88)` | 178 | 23.6% |
| `BaseEventLoop.run_until_complete (asyncio/base_events.py:678)` | 99 | 13.1% |
| `_run_module_code (<frozen runpy>:98)` | 99 | 13.1% |
| `<module> (frame_counter.py:95)` | 99 | 13.1% |
| `<module> (radical-orbit-broker.py:128)` | 99 | 13.1% |
| `Runner.run (asyncio/runners.py:118)` | 99 | 13.1% |
| `Server.run (uvicorn/server.py:86)` | 99 | 13.1% |
| `_run_code (<frozen runpy>:88)` | 99 | 13.1% |
| `run_path (<frozen runpy>:287)` | 99 | 13.1% |

| self (busy leaf) | samples | share |
|---|---|---|
| `_dump (frame_counter.py:79)` | 484 | 64.1% |
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 52 | 6.9% |
| `BaseSelectorEventLoop._write_to_self (asyncio/selector_events.py:152)` | 31 | 4.1% |
| `decode (digitaltwin/service/wire.py:135)` | 11 | 1.5% |
| `Handle._run (asyncio/events.py:88)` | 11 | 1.5% |
| `SSLObject.write (ssl.py:867)` | 6 | 0.8% |
| `WorkflowEngine._create_component (asyncflow/workflow_manager.py:843)` | 6 | 0.8% |
| `Handle.__init__ (asyncio/events.py:36)` | 5 | 0.7% |
| `run_coroutine_threadsafe (asyncio/tasks.py:931)` | 5 | 0.7% |
| `uuid4 (uuid.py:725)` | 5 | 0.7% |
| `packb (msgpack/__init__.py:36)` | 5 | 0.7% |
| `Condition.__enter__ (threading.py:299)` | 4 | 0.5% |
| `Plugin._request_header.<locals>.<genexpr> (orbit/plugin_base.py:606)` | 4 | 0.5% |
| `TimerHandle.__init__ (asyncio/events.py:111)` | 4 | 0.5% |
| `Pickler.dump (cloudpickle/cloudpickle.py:1313)` | 4 | 0.5% |
