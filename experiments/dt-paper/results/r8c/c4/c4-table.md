## (a) swap a running investigator: to the first answer from the new one, p50 ms

| config | dragon_native (r8c) | round 3 T5 |
|---|---|---|
| local c=1 | 1.84 (1.79-1.96) | 0.77 (0.74-1.12) |
| local c=50 | 27.10 (23.74-30.71) | 16.51 (16.17-17.21) |
| ORBIT c=1 | 5.11 (4.90-5.35) | 5.12 (4.16-6.05) |
| ORBIT c=50 | 74.84 (62.49-76.48) | 169.61 (163.89-179.83) |

## (b) a new model, publish to first answer that uses it, p50 ms (intervals pooled)

| path | dragon_native (r8c) | original | versions seen (r8c) |
|---|---|---|---|
| local | 1.83 (1.58-1.94) | 0.66 (0.63-1.01) | 1.0s: 10/10; 0.1s: 100/100; 0.01s: 500/500 |
| ORBIT | 4.95 (4.61-6.09) | 7.07 (5.25-8.21) | 1.0s: 10/10; 0.1s: 100/100; 0.01s: 487/500 |
| radical.3 (WAN) | 521.80 (476.22-547.43) | 517.28 (506.33-546.62) | 1.0s: 10/10; 0.1s: 29/100; 0.01s: 15/500 |

## (c) inference throughput while publishing models, ratio to none (median of repeats, min-max)

| concurrency | rate /s | dragon_native (r8c) | round 3 (T4 c=1, T5 dip c=50) |
|---|---|---|---|
| c=1 | 1 | 1.02 (1.00-1.02) | 0.97 (0.95-1.01) |
| c=1 | 10 | 1.02 (1.01-1.03) | 0.98 (0.96-1.01) |
| c=1 | 100 | 1.04 (1.02-1.06) | 0.98 (0.96-0.98) |
| c=1 | 0 (req/s) | 1,063 (1,013-1,088) | 1,675 (1,669-1,794) |
| c=50 | 1 | 1.00 (0.95-1.08) | 0.99 (0.94-0.99) |
| c=50 | 10 | 1.05 (0.93-1.16) | 0.94 (0.94-1.00) |
| c=50 | 100 | 1.07 (0.93-1.15) | 0.96 (0.92-0.97) |
| c=50 | 0 (req/s) | 2,776 (2,724-3,068) | 3,063 (2,927-3,099) |
