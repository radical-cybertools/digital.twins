| N | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 1 | 2.0 | 2.041 | 206.2 | 4.8 | 5.9 | 0 | 61 | 105 | 71 | 44 |
| 4 | 2 | 4 | 0.6 | 0.140 | 374.0 | 10.3 | 14.9 | 0 | 93 | 118 | 108 | 71 |
| 16 | 2 | 16 | 0.6 | 0.039 | 608.9 | 25.1 | 54.1 | 0 | 96 | 132 | 132 | 179 |
| 64 | 2 | 64 | 1.9 | 0.030 | 777.0 | 77.1 | 233.7 | 0 | 84 | 169 | 228 | 611 |
| 128 | 2 | 128 | 2.2 | 0.017 | 830.1 | 142.3 | 353.4 | 0 | 77 | 229 | 356 | 1187 |
| 256 | 2 | 256 | 3.9 | 0.015 | 842.1 | 278.3 | 712.4 | 0 | 72 | 348 | 612 | 2339 |
| 384 | 2 | 384 | 5.7 | 0.015 | 794.8 | 446.8 | 890.7 | 0 | 68 | 468 | 868 | 3491 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61222333: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
- r2-61222333: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
