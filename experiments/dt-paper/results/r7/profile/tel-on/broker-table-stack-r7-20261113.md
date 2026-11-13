| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 256 | 1 | 256 | 55.3 | 0.216 | 49.1 | 4861.2 | 7466.5 | 0 | 39 | 848 | 1378 | 4380 | 100 | 303 | 613 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225637: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
