| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 256 | 1 | 256 | 70.0 | 0.274 | 28.8 | 8715.0 | 10042.2 | 0 | 32 | 806 | 1378 | 4380 | 195 | 342 | 613 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61226377: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
