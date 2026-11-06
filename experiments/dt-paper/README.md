# DT paper experiments

Code, HOWTOs and small results for the experiments of the DT Framework +
DTaaS paper.  The paper source lives in Overleaf (project
`6ac8e9cce149bcee62db5ecb`, git: `https://git.overleaf.com/6ac8e9cce149bcee62db5ecb`,
GitHub mirror `radical-cybertools/2026-DTaaS`); its evaluation section
mirrors the list below.

Tasks are no-ops unless noted, so the runs isolate DT overhead.  Upper
bounds come from the tools underneath: ZMQ, AsyncFlow, ROSE, ORBIT.

| Dir                | Experiment                                           | State            |
|--------------------|------------------------------------------------------|------------------|
| `bounds/`          | asyncio / AsyncFlow no-op rates (upper bounds)        | scripts          |
| `e1-overhead/`     | E1 Overhead: do the abstractions cost performance?    | in-situ harness, laptop smoke |
| `e2-scaling/`      | E2 Scaling: inputs per second and DT size             | placeholder plots |
| `e3-portability/`  | E3 Portability: same DT on 1 to N sites               | not started      |
| `e4-hot-swap/`     | E4 Hot-swap: update components while the DT runs      | not started      |
| `e5-persistence/`  | E5 Persistence: client and endpoint loss, long run    | not started      |
| `e6-use-cases/`    | E6 Use cases: extensibility, qualitatively            | not started      |

Each directory has a `README.md` with the experiment's outline entry,
the HOWTO for its scripts, and the measured numbers.

## Results

- Small results (JSON/CSV, a few kB) are committed under `<exp>/results/`.
- Raw data (session directories, traces, logs) stays on Perlmutter CFS
  and is not committed; the experiment README records its location.
- Every result records the `digital_twins` commit it was measured with.

## Figures for the paper

Final figures (PDF) and the small CSVs behind them are copied into the
paper repo; plots are generated here, not in Overleaf.
