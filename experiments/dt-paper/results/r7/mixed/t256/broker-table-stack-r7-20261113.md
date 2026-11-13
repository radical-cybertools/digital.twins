| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 256 | 1 | 1 | 256 | 5.8 | 5.806 | 875.4 | 274.3 | 473.3 | 0 | 75 | 323 | 612 | 2339 | 84 | 260 | 103 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225659: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
