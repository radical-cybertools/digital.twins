**pyspy-r1-61226377-broker.folded**: 417971 samples, 1544 busy (77.2 busy thread-s, 0% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| asyncio | 819 | 53.0% |
| other | 533 | 34.5% |
| orbit | 98 | 6.3% |
| serialization | 68 | 4.4% |
| websockets | 23 | 1.5% |
| logging | 2 | 0.1% |
| dt service | 1 | 0.1% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread._bootstrap (threading.py:1032)` | 1293 | 83.7% |
| `Thread._bootstrap_inner (threading.py:1075)` | 1293 | 83.7% |
| `Thread.run (threading.py:1012)` | 1293 | 83.7% |
| `BaseEventLoop.run_forever (asyncio/base_events.py:645)` | 979 | 63.4% |
| `BaseEventLoop._run_once (asyncio/base_events.py:1999)` | 970 | 62.8% |
| `Handle._run (asyncio/events.py:88)` | 962 | 62.3% |
| `SSLProtocol._write_appdata (asyncio/sslproto.py:697)` | 703 | 45.5% |
| `_SSLProtocolTransport.write (asyncio/sslproto.py:222)` | 699 | 45.3% |
| `EndpointRuntime._run_transport_thread (orbit/runtime.py:604)` | 582 | 37.7% |
| `_dump (frame_counter.py:79)` | 530 | 34.3% |
| `SSLProtocol._do_write (asyncio/sslproto.py:716)` | 496 | 32.1% |
| `SSLProtocol._process_outgoing (asyncio/sslproto.py:722)` | 491 | 31.8% |

| self (busy leaf) | samples | share |
|---|---|---|
| `_dump (frame_counter.py:79)` | 530 | 34.3% |
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 490 | 31.7% |
| `SSLObject.write (ssl.py:867)` | 211 | 13.7% |
| `BaseSelectorEventLoop._write_to_self (asyncio/selector_events.py:152)` | 80 | 5.2% |
| `BaseModel.__init__ (pydantic/main.py:280)` | 57 | 3.7% |
| `public_plugins (orbit/protocol.py:90)` | 43 | 2.8% |
| `parse_message (orbit/protocol.py:368)` | 24 | 1.6% |
| `SystemRandom.randbytes (random.py:901)` | 9 | 0.6% |
| `EndpointRuntime._on_frame (orbit/runtime.py:912)` | 7 | 0.5% |
| `BaseModel.model_dump (pydantic/main.py:520)` | 7 | 0.5% |
| `public_topology (orbit/protocol.py:97)` | 6 | 0.4% |
| `EndpointRuntime._on_topology (orbit/runtime.py:1372)` | 6 | 0.4% |
