## p50 per request, ms (median of repeats, min-max)

| path | row | dragon_native, no-op (r8d) | round 3b (concurrent pool / endpoint) |
|---|---|---|---|
| local | bare | 0.91 (0.90-0.98) | 0.58 (0.58-0.59) |
| local | investigator | 0.98 (0.88-1.00) | 0.59 (0.59-0.65) |
| local | agent | 1.00 (0.99-1.00) | 0.60 (0.59-0.61) |
| local | xgf | 1.30 (1.26-1.34) | 0.87 (0.86-0.88) |
| ORBIT cross-node | bare | 3.38 (3.27-3.45) | 2.96 (2.83-3.14) |
| ORBIT cross-node | investigator | 3.36 (3.25-3.41) | 2.87 (2.82-2.96) |
| ORBIT cross-node | agent | 3.29 (3.24-3.36) | 3.01 (2.70-3.36) |
| ORBIT cross-node | xgf | 3.60 (3.49-3.73) | 3.22 (2.96-3.67) |
| radical.3 client | bare | 348.62 (341.65-354.65) | 353.91 (351.73-359.33) |
| radical.3 client | investigator | 348.34 (341.46-354.65) | 353.98 (351.62-359.40) |
| radical.3 client | agent | 348.46 (341.53-354.74) | 353.85 (351.73-359.29) |

## throughput under bursts of 500, req/s (per run median of bursts 2-5; median of repeats, min-max)

| path | row | dragon_native, no-op (r8d) | round 3b |
|---|---|---|---|
| local | bare | 3,073 (2,918-3,197) | 3,672 (3,512-3,768) |
| local | investigator | 2,949 (2,730-3,236) | 3,462 (3,378-3,527) |
| local | agent | 2,768 (2,696-2,878) | 3,025 (2,987-3,232) |
| local | xgf | 2,162 (2,083-2,249) | 2,506 (2,465-2,622) |
| ORBIT cross-node | bare | 1,095 (1,082-1,165) | 1,064 (1,030-1,124) |
| ORBIT cross-node | investigator | 1,074 (1,035-1,105) | 1,035 (963-1,084) |
| ORBIT cross-node | agent | 1,072 (1,029-1,107) | 1,006 (951-1,055) |
| ORBIT cross-node | xgf | 963 (912-992) | 967 (904-984) |
