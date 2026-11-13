| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 64 | 4 | 1 | 256 | 5.5 | 1.374 | 893.6 | 275.4 | 550.8 | 0 | 88 | 325 | 621 | 2363 | 103 | 335 | 233 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225659: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
