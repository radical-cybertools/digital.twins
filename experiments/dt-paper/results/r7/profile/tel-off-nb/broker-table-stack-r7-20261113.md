| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 256 | 1 | 256 | 59.7 | 0.233 | 231.5 | 1026.8 | 1491.2 | 0 | 98 | 750 | 1378 | 4380 | 38 | 205 | 356 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61226377: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
