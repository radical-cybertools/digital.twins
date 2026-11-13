| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 1 | 256 | 1 | 256 | 76.7 | 0.300 | 20.0 | 12400.2 | 13853.8 | 0 | 38 | 761 | 1377 | 4379 | 196 | 327 | 613 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225659: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
