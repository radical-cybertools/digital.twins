| N | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 1 | 2.0 | 2.042 | 198.2 | 5.0 | 6.0 | 0 | 59 | 87 | 71 | 44 |
| 4 | 2 | 4 | 0.6 | 0.143 | 318.5 | 12.2 | 17.9 | 0 | 113 | 105 | 117 | 95 |
| 16 | 2 | 16 | 0.8 | 0.053 | 360.7 | 42.5 | 90.7 | 0 | 118 | 145 | 177 | 299 |
| 64 | 2 | 64 | 3.1 | 0.048 | 303.6 | 200.0 | 502.6 | 0 | 107 | 273 | 417 | 1115 |
| 128 | 2 | 128 | 8.6 | 0.067 | 113.5 | 1160.1 | 1542.1 | 0 | 55 | 473 | 737 | 2203 |
| 256 | 2 | 256 | 49.7 | 0.194 | 23.6 | 10292.9 | 12035.5 | 0 | 30 | 931 | 1377 | 4379 |
| 384 | 2 | 384 | 162.1 | 0.422 | 11.9 | 27199.6 | 33724.4 | 0 | 34 | 1527 | 2017 | 6555 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61221797: 0 timeouts, stopped: no (all N ran), ping timeout 20
- r2-61221797: 0 timeouts, stopped: no (all N ran), ping timeout 20
