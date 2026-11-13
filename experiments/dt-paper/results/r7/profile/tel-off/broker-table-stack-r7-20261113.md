| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 256 | 1 | 256 | 62.2 | 0.243 | 79.1 | 3387.6 | 4738.7 | 0 | 51 | 779 | 1378 | 4380 | 59 | 211 | 356 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225637: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
