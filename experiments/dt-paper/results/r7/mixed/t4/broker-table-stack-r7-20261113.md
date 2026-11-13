| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 4 | 64 | 1 | 256 | 9.5 | 0.149 | 395.8 | 631.3 | 951.8 | 0 | 107 | 378 | 801 | 2843 | 153 | 464 | 956 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225659: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
