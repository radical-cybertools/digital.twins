# Paper figures

`make_figures.py` reads the committed result JSON under `../results/` and
writes one PDF per figure, plus `manifest.json` with the source files and
the digital_twins commit of every figure.  It needs only matplotlib.

```sh
python3 experiments/dt-paper/plots/make_figures.py --out <paper repo>/figures
python3 experiments/dt-paper/plots/make_figures.py --out ... --only e1-paths,e5-endpoint-loss
```

- Only paper-stack results are plotted (rounds 2 to 4, `STACK.md`).
  P8a's surrogate costs are from round 1; they do not depend on the stack.
- Points are medians over repeats; error bars span min to max, except
  `e6-windfield` (b), which shows p10 to p90 of the probes.
- `e1-paths`: local pool and ORBIT cross-node from round 3b U2, each row
  (xgf included) in its own process; radical.3 client from U3; the service
  bar is round 2's S3.  Throughput is the median of bursts 2-5: a single
  burst varies with where the client's garbage collector runs (U4b/U4c).
- `e1-inprocess`: U2's solo against in-one-process ratios through ORBIT,
  with round 2c's in-process ratios (before finished tasks were released)
  as markers.
- Sizes fit the paper's current `article` class (4.8 in wide); redo them for
  the final template.

| Figure | Section | Sources |
|---|---|---|
| `e1-paths` | E1 | `r3b/u2` (solo, xgf), `r3b/u3`, `s3` |
| `e1-inprocess` | E1 | `r3b/u2` (solo, inproc), `c3/p4` |
| `e1-pool` | E1 | `r3c/v1` (c=500, bursts 2-5) |
| `e1-exsitu` | E1 | `r3b/u5` (bare, zmq, dt, dt-batched) |
| `e2-scaling` | E2 | `r3/t4` twins, joins |
| `e2-agents-broker` | E2 | `r3/t4` agents, broker capacity |
| `e3-sites` | E3 | `r4/local` (dt and xgf, spread and one), `r4/remote` |
| `e4-propagation` | E4 | `r3/t5` update, `s2/update-*` |
| `e4-swap` | E4 | `r3/t5` swap, dip; `r3/t4` publish |
| `e5-endpoint-loss` | E5 | `s2`, `b1`, `c1`, `c2` |
| `e6-windfield` | E6 | `p8/surrogate-*`, `b3` |

`e3-sites` (E3, round 4) reads `results/r4/local/` and `results/r4/remote/`.
