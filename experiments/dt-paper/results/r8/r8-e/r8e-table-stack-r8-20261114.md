
### warm0 (reload per call, as xGFabric): 3 runs, 984 answers

| model | n | total | to task start | in task | setup | extract | reload | field | cleanup | return | cached share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pinn | 535 | 155.4 | 16.1 | 134.5 | 1.8 | 31.3 | 81.8 | 16.6 | 2.0 | 4.4 | 0.00 |
| fno | 109 | 817.8 | 14.8 | 795.3 | 1.7 | 116.0 | 563.2 | 115.0 | 4.4 | 6.1 | 0.00 |
| na | 340 | 12.5 | 9.7 | 0.0 | – | – | – | – | – | 2.6 | – |

selector task: n=4587, p50 0.00 ms
training fno: n=10, p50 260.2 s (min 239.1, max 331.3)
training pcr:tk_do_pcr: n=72, p50 7.3 s (min 6.8, max 8.2)
training pcr:tk_pcr_partition: n=9, p50 290.3 s (min 265.2, max 346.1)
training pinn: n=8, p50 353.9 s (min 320.8, max 416.7)
choices by time quarter: na 1.00 | na 0.28, pinn 0.49, fno 0.23 | pinn 0.69, fno 0.31 | pinn 1.00

### warm1 (warm model per worker): 3 runs, 968 answers

| model | n | total | to task start | in task | setup | extract | reload | field | cleanup | return | cached share |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pinn | 417 | 42.9 | 16.9 | 20.9 | 1.7 | 0.0 | 0.0 | 17.5 | 0.9 | 4.1 | 0.77 |
| fno | 217 | 178.8 | 15.6 | 151.9 | 1.7 | 0.0 | 0.0 | 115.2 | 1.2 | 5.7 | 0.51 |
| na | 334 | 11.9 | 9.1 | 0.0 | – | – | – | – | – | 2.5 | – |

selector task: n=4568, p50 0.00 ms
training fno: n=11, p50 248.8 s (min 209.5, max 324.5)
training pcr:tk_do_pcr: n=72, p50 7.3 s (min 6.6, max 7.8)
training pcr:tk_pcr_partition: n=9, p50 262.3 s (min 235.3, max 331.2)
training pinn: n=9, p50 316.0 s (min 302.4, max 406.8)
choices by time quarter: na 1.00 | na 0.24, pinn 0.43, fno 0.34 | pinn 0.55, fno 0.45 | pinn 0.77, fno 0.23
