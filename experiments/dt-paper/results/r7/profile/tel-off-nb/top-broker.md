**pyspy-r1-61226377-broker.folded**: 386262 samples, 2385 busy (119.2 busy thread-s, 1% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| asyncio | 1525 | 63.9% |
| other | 503 | 21.1% |
| orbit | 149 | 6.2% |
| serialization | 123 | 5.2% |
| logging | 43 | 1.8% |
| websockets | 37 | 1.6% |
| asyncflow | 3 | 0.1% |
| rhapsody | 2 | 0.1% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread._bootstrap_inner (threading.py:1075)` | 1895 | 79.5% |
| `Thread.run (threading.py:1012)` | 1895 | 79.5% |
| `Thread._bootstrap (threading.py:1032)` | 1895 | 79.5% |
| `BaseEventLoop.run_forever (asyncio/base_events.py:645)` | 1755 | 73.6% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 1744 | 73.1% |
| `Handle._run (asyncio/events.py:88)` | 1738 | 72.9% |
| `SSLProtocol._write_appdata (asyncio/sslproto.py:697)` | 1208 | 50.6% |
| `_SSLProtocolTransport.write (asyncio/sslproto.py:222)` | 1206 | 50.6% |
| `EndpointRuntime._run_transport_thread (orbit/runtime.py:604)` | 983 | 41.2% |
| `SSLProtocol._do_write (asyncio/sslproto.py:716)` | 898 | 37.7% |
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 892 | 37.4% |
| `SSLProtocol._process_outgoing (asyncio/sslproto.py:722)` | 891 | 37.4% |

| self (busy leaf) | samples | share |
|---|---|---|
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 892 | 37.4% |
| `_dump (frame_counter.py:79)` | 501 | 21.0% |
| `SSLObject.write (ssl.py:867)` | 314 | 13.2% |
| `BaseSelectorEventLoop._write_to_self (asyncio/selector_events.py:152)` | 247 | 10.4% |
| `BaseModel.__init__ (pydantic/main.py:280)` | 99 | 4.2% |
| `public_plugins (orbit/protocol.py:90)` | 50 | 2.1% |
| `StreamHandler.flush (logging/__init__.py:1144)` | 39 | 1.6% |
| `parse_message (orbit/protocol.py:368)` | 33 | 1.4% |
| `Handle._run (asyncio/events.py:88)` | 18 | 0.8% |
| `BaseModel.model_dump (pydantic/main.py:520)` | 15 | 0.6% |
| `EndpointRuntime._on_frame (orbit/runtime.py:912)` | 9 | 0.4% |
| `uuid4 (uuid.py:725)` | 8 | 0.3% |
