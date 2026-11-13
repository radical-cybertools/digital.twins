| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 256 | 16 | 16 | 1 | 256 | 6.3 | 0.394 | 712.4 | 336.4 | 698.6 | 0 | 103 | 317 | 657 | 2459 | 119 | 417 | 629 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225659: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
