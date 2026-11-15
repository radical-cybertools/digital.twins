## p50 per request, ms (median of repeats, min-max)

| path | row | dragon_native (r8c) | round 3b (concurrent pool / endpoint) |
|---|---|---|---|
| local | bare | 1.57 (1.48-1.58) | 0.58 (0.58-0.59) |
| local | investigator | 1.59 (1.57-1.59) | 0.59 (0.59-0.65) |
| local | agent | 1.56 (1.54-1.60) | 0.60 (0.59-0.61) |
| local | xgf | 1.84 (1.82-1.87) | 0.87 (0.86-0.88) |
| ORBIT cross-node | bare | 3.80 (3.73-3.91) | 2.96 (2.83-3.14) |
| ORBIT cross-node | investigator | 3.77 (3.67-3.83) | 2.87 (2.82-2.96) |
| ORBIT cross-node | agent | 3.81 (3.69-3.93) | 3.01 (2.70-3.36) |
| ORBIT cross-node | xgf | 4.09 (4.00-4.17) | 3.22 (2.96-3.67) |
| radical.3 client | bare | 350.11 (345.73-357.72) | 353.91 (351.73-359.33) |
| radical.3 client | investigator | 350.13 (345.67-357.64) | 353.98 (351.62-359.40) |
| radical.3 client | agent | 350.25 (345.66-357.71) | 353.85 (351.73-359.29) |
| radical.3 service | bare (twin in the broker's dt plugin) | 516.47 (516.20-516.48) | 346.37 (346.18-346.43) |

## throughput under bursts of 500, req/s (per run median of bursts 2-5; median of repeats, min-max)

| path | row | dragon_native (r8c) | round 3b |
|---|---|---|---|
| local | bare | 3,082 (2,863-3,346) | 3,672 (3,512-3,768) |
| local | investigator | 2,801 (2,739-2,958) | 3,462 (3,378-3,527) |
| local | agent | 2,748 (2,689-2,920) | 3,025 (2,987-3,232) |
| local | xgf | 2,062 (1,992-2,245) | 2,506 (2,465-2,622) |
| ORBIT cross-node | bare | 1,145 (1,055-1,179) | 1,064 (1,030-1,124) |
| ORBIT cross-node | investigator | 1,068 (1,042-1,085) | 1,035 (963-1,084) |
| ORBIT cross-node | agent | 1,024 (1,001-1,094) | 1,006 (951-1,055) |
| ORBIT cross-node | xgf | 953 (897-990) | 967 (904-984) |

Service: session + twin 2.90 s (S3 1.51), reattach 10/10 in 1.07 s (S3 10/10 in 1.06 s), first answer after reattach 1.75 s (S3 1.59).
