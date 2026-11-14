| row | twins | repeats | p50 ms | p99 ms | worst twin p99 ms | burst s p50 / max | update delay s p50 / max | probes / failed | broker CPU % | inference endpoint CPU % | break |
|---|---|---|---|---|---|---|---|---|---|---|---|
| onesession | 1 | 2 | 36.2 | 301 | 303 | 0.28 / 0.29 | 1.10 / 8.00 | 120 / 0 | 4 | 137 | – |
| onesession | 4 | 2 | 42.8 | 263 | 324 | 0.30 / 0.38 | 0.86 / 7.89 | 480 / 0 | 9 | 155 | – |
| onesession | 16 | 2 | 64.7 | 263 | 353 | 0.37 / 0.64 | 0.76 / 7.78 | 1920 / 0 | 28 | 193 | – |
| onesession | 64 | 2 | 148.0 | 1249 | 1597 | 0.81 / 1.42 | 1.06 / 8.78 | 7603 / 0 | 83 | 205 | p99 1034 ms; p99 1464 ms |
| onesession | 128 | 2 | 1287.6 | 2768 | 3366 | 1.05 / 2.62 | 1.88 / 12.89 | 10571 / 0 | 113 | 161 | p99 2387 ms; p99 3148 ms |
