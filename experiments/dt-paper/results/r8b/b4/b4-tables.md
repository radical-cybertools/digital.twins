
## b4base (300 probes, 40 bursts seen, failed 0)

| arch | probes | p50 ms | p99 ms | max ms |
|---|---|---|---|---|
| pinn | 248 | 33.5 | 36.8 | 143.4 |
| fno | 52 | 133.8 | 137.0 | 137.2 |
| all | 300 | 33.8 | 136.1 | 143.4 |

burst starts: 40, period p50 0.0 s (min 0.0, max 16.0); makespan p50 0.28 s

slowest 10:

| t (s into load) | arch | lat ms | to nearest burst start s | submit+run ms | return ms |
|---|---|---|---|---|---|
| 165.0 | pinn | 143 | -2.3 | 140 | 3 |
| 63.0 | fno | 137 | +7.9 | 133 | 5 |
| 58.0 | fno | 137 | +2.9 | 134 | 3 |
| 43.0 | fno | 136 | +3.9 | 133 | 4 |
| 30.0 | fno | 136 | +6.9 | 133 | 3 |
| 84.0 | fno | 135 | -3.2 | 132 | 4 |
| 259.0 | fno | 135 | -4.4 | 132 | 4 |
| 65.0 | fno | 135 | -6.2 | 130 | 5 |
| 126.0 | fno | 135 | +6.8 | 131 | 4 |
| 6.0 | fno | 135 | -1.1 | 130 | 5 |

pinn median split: submit+run 30.2 ms, return 3.2 ms (248 probes)

fno median split: submit+run 130.2 ms, return 3.5 ms (52 probes)

## b4noburst (300 probes, 0 bursts seen, failed 0)

| arch | probes | p50 ms | p99 ms | max ms |
|---|---|---|---|---|
| pinn | 229 | 33.6 | 37.5 | 38.0 |
| fno | 71 | 133.9 | 137.4 | 137.5 |
| all | 300 | 34.0 | 136.5 | 137.5 |

slowest 10:

| t (s into load) | arch | lat ms | to nearest burst start s | submit+run ms | return ms |
|---|---|---|---|---|---|
| 39.0 | fno | 138 | – | 134 | 4 |
| 48.0 | fno | 137 | – | 132 | 5 |
| 51.0 | fno | 137 | – | 131 | 6 |
| 34.0 | fno | 136 | – | 133 | 3 |
| 53.0 | fno | 136 | – | 131 | 5 |
| 50.0 | fno | 136 | – | 132 | 4 |
| 130.0 | fno | 136 | – | 132 | 4 |
| 67.0 | fno | 135 | – | 132 | 4 |
| 41.0 | fno | 135 | – | 131 | 5 |
| 258.0 | fno | 135 | – | 131 | 4 |

pinn median split: submit+run 30.3 ms, return 3.3 ms (229 probes)

fno median split: submit+run 130.2 ms, return 3.5 ms (71 probes)

## b4nostream (300 probes, 0 bursts seen, failed 0)

| arch | probes | p50 ms | p99 ms | max ms |
|---|---|---|---|---|
| pinn | 250 | 34.7 | 201.0 | 225.2 |
| fno | 50 | 134.9 | 301.9 | 305.6 |
| all | 300 | 35.1 | 225.9 | 305.6 |

slowest 10:

| t (s into load) | arch | lat ms | to nearest burst start s | submit+run ms | return ms |
|---|---|---|---|---|---|
| 10.0 | fno | 306 | – | 302 | 4 |
| 12.0 | fno | 298 | – | 295 | 3 |
| 11.0 | fno | 297 | – | 294 | 4 |
| 9.0 | pinn | 225 | – | 222 | 4 |
| 16.0 | pinn | 205 | – | 202 | 3 |
| 15.0 | pinn | 201 | – | 197 | 4 |
| 20.0 | pinn | 201 | – | 197 | 4 |
| 17.0 | pinn | 199 | – | 196 | 4 |
| 8.0 | pinn | 199 | – | 196 | 4 |
| 14.0 | pinn | 199 | – | 195 | 4 |

pinn median split: submit+run 31.2 ms, return 3.4 ms (250 probes)

fno median split: submit+run 131.3 ms, return 3.5 ms (50 probes)
