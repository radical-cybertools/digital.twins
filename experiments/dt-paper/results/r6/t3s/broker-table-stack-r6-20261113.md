| N | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 1 | 2.0 | 2.043 | 200.8 | 5.0 | 5.9 | 0 | 60 | 85 | 71 | 44 |
| 4 | 2 | 4 | 0.6 | 0.142 | 316.8 | 12.3 | 18.0 | 0 | 113 | 107 | 117 | 95 |
| 16 | 2 | 16 | 0.8 | 0.047 | 352.7 | 43.3 | 96.0 | 0 | 119 | 147 | 177 | 299 |
| 64 | 2 | 64 | 3.4 | 0.052 | 328.8 | 186.3 | 374.2 | 0 | 116 | 272 | 417 | 1115 |
| 128 | 2 | 128 | 9.7 | 0.076 | 79.0 | 1604.6 | 1978.8 | 0 | 46 | 466 | 737 | 2203 |
| 256 | 2 | 256 | 63.6 | 0.248 | 19.7 | 12467.8 | 14139.4 | 0 | 31 | 911 | 1377 | 4379 |
| 384 | 2 | 384 | 181.2 | 0.472 | 11.2 | 27313.1 | 35654.0 | 0 | 36 | 1513 | 2017 | 6555 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61219149: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
- r2-61219149: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
