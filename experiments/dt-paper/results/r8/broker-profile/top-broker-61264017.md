**pyspy-profiled-61264017-broker.folded**: 17574 samples, 800 busy (40.0 busy thread-s, 5% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| other | 495 | 61.9% |
| asyncio | 148 | 18.5% |
| orbit | 54 | 6.8% |
| logging | 42 | 5.2% |
| dt service | 24 | 3.0% |
| websockets | 13 | 1.6% |
| asyncflow | 10 | 1.2% |
| serialization | 8 | 1.0% |
| rhapsody | 6 | 0.8% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread._bootstrap_inner (threading.py:1075)` | 631 | 78.9% |
| `Thread.run (threading.py:1012)` | 631 | 78.9% |
| `Thread._bootstrap (threading.py:1032)` | 631 | 78.9% |
| `_dump (frame_counter.py:79)` | 488 | 61.0% |
| `BaseEventLoop.run_forever (asyncio/base_events.py:645)` | 227 | 28.4% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 221 | 27.6% |
| `Handle._run (asyncio/events.py:88)` | 219 | 27.4% |
| `_run_module_code (<frozen runpy>:98)` | 102 | 12.8% |
| `Runner.run (asyncio/runners.py:118)` | 102 | 12.8% |
| `BaseEventLoop.run_until_complete (asyncio/base_events.py:678)` | 102 | 12.8% |
| `<module> (frame_counter.py:95)` | 102 | 12.8% |
| `Broker.run (orbit/broker.py:712)` | 102 | 12.8% |
| `main (radical-orbit-broker.py:124)` | 102 | 12.8% |
| `Server.run (uvicorn/server.py:86)` | 102 | 12.8% |
| `run_path (<frozen runpy>:287)` | 102 | 12.8% |
| `run (uvicorn/main.py:632)` | 102 | 12.8% |
| `run (asyncio/runners.py:195)` | 102 | 12.8% |
| `_run_code (<frozen runpy>:88)` | 102 | 12.8% |
| `<module> (radical-orbit-broker.py:128)` | 102 | 12.8% |
| `Broker._start_host_thread.<locals>._run (orbit/broker.py:551)` | 95 | 11.9% |
| `SSLProtocol._write_appdata (asyncio/sslproto.py:697)` | 53 | 6.6% |
| `_SSLProtocolTransport.write (asyncio/sslproto.py:222)` | 52 | 6.5% |
| `WebSocketsSansIOProtocol.send (uvicorn/protocols/websockets/websockets_sansio_impl.py:506)` | 52 | 6.5% |
| `wrap_app_handling_exceptions.<locals>.wrapped_app.<locals>.sender (starlette/_exception_handler.py:39)` | 52 | 6.5% |
| `WebSocket.send_bytes (starlette/websockets.py:175)` | 49 | 6.1% |

| self (busy leaf) | samples | share |
|---|---|---|
| `_dump (frame_counter.py:79)` | 488 | 61.0% |
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 36 | 4.5% |
| `BaseSelectorEventLoop._write_to_self (asyncio/selector_events.py:152)` | 31 | 3.9% |
| `StreamHandler.flush (logging/__init__.py:1144)` | 29 | 3.6% |
| `Handle._run (asyncio/events.py:88)` | 14 | 1.8% |
| `decode (digitaltwin/service/wire.py:135)` | 12 | 1.5% |
| `SSLObject.write (ssl.py:867)` | 11 | 1.4% |
| `uuid4 (uuid.py:725)` | 6 | 0.8% |
| `_chain_future (asyncio/futures.py:367)` | 6 | 0.8% |
| `_key (frame_counter.py:48)` | 5 | 0.6% |
| `` | 5 | 0.6% |
| `Logger.makeRecord (logging/__init__.py:1651)` | 5 | 0.6% |
| `WorkflowEngine.task_callbacks (asyncflow/workflow_manager.py:2292)` | 4 | 0.5% |
| `DTSession.twin_call (digitaltwin/service/session.py:382)` | 4 | 0.5% |
| `__newobj__ (copyreg.py:99)` | 4 | 0.5% |
| `Broker._route_frame (orbit/broker.py:893)` | 3 | 0.4% |
| `_key (frame_counter.py:44)` | 3 | 0.4% |
| `run_coroutine_threadsafe (asyncio/tasks.py:931)` | 3 | 0.4% |
| `Broker._dispatch_to_host (orbit/broker.py:1009)` | 3 | 0.4% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 3 | 0.4% |
| `_route_frame (frame_counter.py:62)` | 3 | 0.4% |
| `RhapsodyClient._serialize_task (orbit/plugin_rhapsody.py:1872)` | 2 | 0.2% |
| `RhapsodyClient._serialize_task (orbit/plugin_rhapsody.py:1859)` | 2 | 0.2% |
| `packb (msgpack/__init__.py:36)` | 2 | 0.2% |
| `Broker._dispatch_to_host (orbit/broker.py:1011)` | 2 | 0.2% |
