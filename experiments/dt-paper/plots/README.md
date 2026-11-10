# Paper figures

`make_figures.py` reads the committed result JSON under `../results/` and
writes one PDF per figure, plus `manifest.json` with the source files and
the digital_twins commit of every figure.  It needs only matplotlib.

```sh
python3 experiments/dt-paper/plots/make_figures.py --out <paper repo>/figures
python3 experiments/dt-paper/plots/make_figures.py --out ... --only e1-paths,e5-endpoint-loss
```

- Only paper-stack results are plotted (rounds 2, 2b, 2c and 3, `STACK.md`).
  P8a's surrogate costs are from round 1; they do not depend on the stack.
- Points are medians over repeats; error bars span min to max, except
  `e6-windfield` (b), which shows p10 to p90 of the probes.
- `e1-paths`: local pool and ORBIT cross-node from round 3 T3, each row
  (xgf included) in its own process; (b) is the median of bursts 2-5.  Round 3
  ran before the task-release fixes, so its bursts still carry rhapsody's task
  leak (T1); a rerun on the fixed stack replaces them.
- Sizes fit the paper's current `article` class (4.8 in wide); redo them for
  the final template.

| Figure | Section | Sources |
|---|---|---|
| `e1-paths` | E1 | `r3/t3` (solo, xgf), `c3/r1`, `s3` |
| `e1-pool` | E1 | `s1/p1` (c=500) |
| `e1-exsitu` | E1 | `r3/t2` (bare, zmq, dt, dt-batched) |
| `e2-scaling` | E2 | `r3/t4` twins, joins |
| `e2-agents-broker` | E2 | `r3/t4` agents, broker capacity |
| `e4-propagation` | E4 | `r3/t5` update, `s2/update-*` |
| `e4-swap` | E4 | `r3/t5` swap, dip; `r3/t4` publish |
| `e5-endpoint-loss` | E5 | `s2`, `b1`, `c1`, `c2` |
| `e6-windfield` | E6 | `p8/surrogate-*`, `b3` |
