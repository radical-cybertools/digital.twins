| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 256 | 1 | 256 | 62.6 | 0.245 | 21.8 | 11364.6 | 12506.4 | 0 | 31 | 837 | 1377 | 4379 | 192 | 307 | 613 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61226377: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
