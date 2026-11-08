# Paper figures

`make_figures.py` reads the committed result JSON under `../results/` and
writes one PDF per figure, plus `manifest.json` with the source files and
the digital_twins commit of every figure.  It needs only matplotlib.

```sh
python3 experiments/dt-paper/plots/make_figures.py --out <paper repo>/figures
python3 experiments/dt-paper/plots/make_figures.py --out ... --only e1-paths,e5-endpoint-loss
```

- Only paper-stack results are plotted (rounds 2, 2b and 2c, `STACK.md`).
  P8a's surrogate costs are from round 1; they do not depend on the stack.
- Points are medians over repeats; error bars span min to max, except
  `e6-windfield` (b), which shows p10 to p90 of the probes.
- `e1-paths` (b), local pool: each row in its own process
  (`results/s1/p1-rerun/*solo*`), because in one process the first DT row
  after bare pays a row-order cost under a burst (journal, S1 P1).
- Sizes fit the paper's current `article` class (4.8 in wide); redo them for
  the final template.

| Figure | Section | Sources |
|---|---|---|
| `e1-paths` | E1 | `s1/p1`, `s1/p1-rerun` (solo), `c3/p4`, `c3/r1`, `s3` |
| `e1-pool` | E1 | `s1/p1` (c=500) |
| `e1-exsitu` | E1 | `s1/p3` |
| `e2-scaling` | E2 | `s1/p5` |
| `e4-propagation` | E4 | `s1/p7`, `s2/update-*` |
| `e5-endpoint-loss` | E5 | `s2`, `b1`, `c1`, `c2` |
| `e6-windfield` | E6 | `p8/surrogate-*`, `b3` |
