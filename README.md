# RADICAL Doppelganger

Digital twins as a service (DTaaS).  A twin is a graph of components
that consumes a live data stream, serves predictions from a model, and
keeps that model current while it runs.  The same twin code runs in your
own process or on a service that keeps it running and places its tasks on
HPC resources, built on
[ORBIT](https://github.com/radical-cybertools/radical.orbit),
[Rhapsody](https://github.com/radical-cybertools/rhapsody),
[AsyncFlow](https://github.com/radical-cybertools/radical.asyncflow) and
[ROSE](https://github.com/radical-cybertools/ROSE).

**Documentation: <https://radicaldoppelganger.readthedocs.io>**, sources
in [`docs/`](docs/).  Start with
[Your first twin](docs/tutorial/first-twin.md).  Doppelganger v1 is a
research prototype; read
[Status and limits](docs/overview/status-and-limits.md) first.

## Quick start

```sh
# pre-release: install the pinned stack from docs/tutorial/install.md, then
git clone -b devel https://github.com/radical-cybertools/digital.twins
cd digital.twins/examples/surrogate
python run_local.py
```

The twin learns a surrogate for a simulation from its own input stream
and exits once the surrogate it serves is accurate.

## Repository

| Path | Contents |
|---|---|
| `src/radical/doppelganger/` | the framework, the `dt` ORBIT plugin (`service/`) and its dashboard (`service/ui/`) |
| `examples/` | the documented examples, run in CI |
| `test/unit/`, `test/integration/` | the test suite |
| `test/NN-*/`, `test/demo/` | one runnable demo per graph pattern |
| `deploy/` | the pinned installer and launchers for deployments |
| `experiments/` | benchmarks for the DTaaS paper |
| `docs/` | the documentation site (MkDocs) |

## Tests

```sh
pip install ".[test,service,learn]"     # pre-release pins: docs/tutorial/install.md
pytest test/unit                        # starts its own stream broker, no setup
pytest test/integration                 # starts an ORBIT broker and two endpoints
```

The integration tests need an ORBIT certificate and token in
`~/.radical/orbit/` and skip themselves without them.  Tests run against
the installed package: reinstall after every change.

In an environment that had this package under its old name, run
`pip uninstall digitaltwin` first; both would register the `dt` plugin.
