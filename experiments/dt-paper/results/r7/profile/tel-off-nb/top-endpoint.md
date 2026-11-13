**pyspy-r1-61226377-endpoint.folded**: 152360 samples, 287 busy (14.3 busy thread-s, 0% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| asyncio | 232 | 80.8% |
| logging | 23 | 8.0% |
| orbit | 21 | 7.3% |
| other | 6 | 2.1% |
| rhapsody | 3 | 1.0% |
| serialization | 1 | 0.3% |
| websockets | 1 | 0.3% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread._bootstrap (threading.py:1032)` | 266 | 92.7% |
| `Thread.run (threading.py:1012)` | 266 | 92.7% |
| `Thread._bootstrap_inner (threading.py:1075)` | 266 | 92.7% |
| `_worker (concurrent/futures/thread.py:93)` | 156 | 54.4% |
| `_WorkItem.run (concurrent/futures/thread.py:59)` | 142 | 49.5% |
| `ConcurrentExecutionBackend._run_in_thread (rhapsody/backends/execution/concurrent.py:154)` | 139 | 48.4% |
| `run (asyncio/runners.py:194)` | 137 | 47.7% |
| `BaseEventLoop.run_forever (asyncio/base_events.py:645)` | 103 | 35.9% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 100 | 34.8% |
| `Handle._run (asyncio/events.py:88)` | 93 | 32.4% |
| `new_event_loop (asyncio/events.py:823)` | 77 | 26.8% |
| `BaseDefaultEventLoopPolicy.new_event_loop (asyncio/events.py:720)` | 77 | 26.8% |

| self (busy leaf) | samples | share |
|---|---|---|
| `socket._real_close (socket.py:499)` | 52 | 18.1% |
| `socketpair (socket.py:659)` | 47 | 16.4% |
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 42 | 14.6% |
| `BaseSelectorEventLoop._write_to_self (asyncio/selector_events.py:152)` | 23 | 8.0% |
| `StreamHandler.flush (logging/__init__.py:1144)` | 19 | 6.6% |
| `_PollLikeSelector.__init__ (selectors.py:349)` | 18 | 6.3% |
| `SSLObject.write (ssl.py:867)` | 11 | 3.8% |
| `_PollLikeSelector.register (selectors.py:359)` | 6 | 2.1% |
| `Handle._run (asyncio/events.py:88)` | 5 | 1.7% |
| `BaseSelectorEventLoop._make_self_pipe (asyncio/selector_events.py:122)` | 4 | 1.4% |
| `match_route (orbit/dispatch.py:94)` | 4 | 1.4% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 4 | 1.4% |
