**pyspy-r1-61226377-endpoint.folded**: 298656 samples, 87599 busy (4379.9 busy thread-s, 29% of samples)

| component (deepest frame) | busy samples | share |
|---|---|---|
| telemetry | 86193 | 98.4% |
| asyncio | 1288 | 1.5% |
| logging | 86 | 0.1% |
| orbit | 10 | 0.0% |
| serialization | 8 | 0.0% |
| other | 7 | 0.0% |
| websockets | 5 | 0.0% |
| rhapsody | 2 | 0.0% |

| inclusive (busy) | samples | share |
|---|---|---|
| `Thread._bootstrap_inner (threading.py:1075)` | 87567 | 100.0% |
| `Thread.run (threading.py:1012)` | 87567 | 100.0% |
| `Thread._bootstrap (threading.py:1032)` | 87567 | 100.0% |
| `ConcurrentTelemetryAdapter._collect_loop (rhapsody/telemetry/adapters/concurrent.py:225)` | 86389 | 98.6% |
| `ConcurrentTelemetryAdapter._collect_loop.<locals>._poll (rhapsody/telemetry/adapters/concurrent.py:161)` | 51734 | 59.1% |
| `disk_io_counters (psutil/__init__.py:2097)` | 51666 | 59.0% |
| `disk_io_counters (psutil/_pslinux.py:1160)` | 41818 | 47.7% |
| `is_storage_device (psutil/_pslinux.py:248)` | 41818 | 47.7% |
| `ConcurrentTelemetryAdapter._collect_loop.<locals>._poll (rhapsody/telemetry/adapters/concurrent.py:136)` | 12278 | 14.0% |
| `virtual_memory (psutil/__init__.py:2017)` | 12276 | 14.0% |
| `ConcurrentTelemetryAdapter._collect_loop.<locals>._poll (rhapsody/telemetry/adapters/concurrent.py:170)` | 12039 | 13.7% |
| `net_io_counters (psutil/__init__.py:2148)` | 12026 | 13.7% |

| self (busy leaf) | samples | share |
|---|---|---|
| `is_storage_device (psutil/_pslinux.py:248)` | 41818 | 47.7% |
| `open_binary (psutil/_common.py:766)` | 11994 | 13.7% |
| `open_text (psutil/_common.py:776)` | 10728 | 12.2% |
| `disk_io_counters.<locals>.read_procfs (psutil/_pslinux.py:1101)` | 4134 | 4.7% |
| `cpu_times (psutil/_pslinux.py:555)` | 3512 | 4.0% |
| `net_io_counters (psutil/_pslinux.py:1000)` | 3279 | 3.7% |
| `virtual_memory (psutil/_pslinux.py:363)` | 3264 | 3.7% |
| `net_io_counters (psutil/_pslinux.py:999)` | 3013 | 3.4% |
| `virtual_memory (psutil/_pslinux.py:362)` | 3007 | 3.4% |
| `cpu_times (psutil/_pslinux.py:554)` | 478 | 0.5% |
| `disk_io_counters.<locals>.read_procfs (psutil/_pslinux.py:1100)` | 408 | 0.5% |
| `_SelectorSocketTransport.write (asyncio/selector_events.py:1075)` | 362 | 0.4% |
