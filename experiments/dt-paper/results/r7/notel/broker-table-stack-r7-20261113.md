| N | T | S | repeats | created | create s | s per session | req/s | p50 ms | p99 ms | failed | broker CPU % | RSS MB | threads | fds | endpoint CPU % | ep RSS MB | ep threads |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 1 | 2 | 1 | 2.0 | 2.044 | 227.1 | 4.3 | 5.3 | 0 | 71 | 98 | 71 | 44 | 43 | 104 | 70 |
| 4 | 1 | 4 | 2 | 4 | 0.6 | 0.141 | 337.9 | 11.7 | 16.3 | 0 | 120 | 115 | 117 | 95 | 59 | 119 | 104 |
| 16 | 1 | 16 | 2 | 16 | 0.8 | 0.049 | 356.3 | 45.2 | 88.7 | 0 | 123 | 151 | 177 | 299 | 57 | 125 | 116 |
| 64 | 1 | 64 | 2 | 64 | 3.2 | 0.050 | 366.9 | 177.5 | 269.1 | 0 | 123 | 282 | 417 | 1115 | 52 | 144 | 164 |
| 128 | 1 | 128 | 2 | 128 | 8.2 | 0.064 | 336.6 | 367.5 | 558.7 | 0 | 122 | 475 | 737 | 2203 | 50 | 176 | 228 |
| 256 | 1 | 256 | 2 | 256 | 39.5 | 0.154 | 291.9 | 835.4 | 1155.0 | 0 | 122 | 930 | 1377 | 4379 | 45 | 222 | 356 |
| 384 | 1 | 384 | 2 | 384 | 306.3 | 0.798 | 256.0 | 1379.4 | 1880.6 | 0 | 122 | 1503 | 2017 | 6555 | 39 | 273 | 484 |

Per repeat: keepalive ping timeouts in the broker log, stop reason, RADICAL_ORBIT_PING_TIMEOUT

- r1-61225635: 2 timeouts, stopped: session creation failed at N=384, ping timeout default (3 s)
- r2-61225635: 0 timeouts, stopped: no (all N ran), ping timeout default (3 s)
