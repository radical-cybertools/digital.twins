# Documentation layout

The site has one section per reader:

| Section | Reader | Holds |
|---|---|---|
| Overview | everyone | what Doppelganger is, the stack, status and limits |
| Build a twin | twin authors | install, tutorials from a first twin to the service |
| Use the service | service users | the client guide, data plane, dashboard, telemetry |
| Operate | operators | deployment, HPC, runbook, troubleshooting (planned) |
| Develop | contributors | this page, design records, contributing (planned) |

Pages are written when a reader needs them.  The planned sections get
pages as deployments and contributors appear; until then their content
lives in `deploy/`, `test/12-dtaas-live/RUNBOOK.md` and the design pages.

## Rules

- **One fact, one place.**  Limits live in
  [Status and limits](../overview/status-and-limits.md); other pages link
  there.  Layer facts live in that layer's docs; this site links them.
- **Code is included, not copied.**  Tutorials include code from
  `examples/` with snippets (`--8<-- "examples/surrogate/surrogate.py:inference"`,
  sections marked by `# --8<-- [start:name]` / `[end:name]` comments), and
  the examples run in CI (`test/unit/test_examples.py`,
  `test/integration/test_service_examples.py`).  A tutorial that runs is
  a tutorial that is right.
- **Generated where the code knows better.**  The pre-release install
  pins are rendered from `deploy/install.sh` by
  `docs/hooks/stack_pins.py`.  Remove the hook and its marker once the
  stack installs from PyPI.
- **Design records are history.**  Pages under *Design* explain why
  things are as they are; they are not updated to track the code.

## Build

```sh
pip install -r docs/requirements.txt
mkdocs serve            # live preview on http://127.0.0.1:8000
mkdocs build --strict   # what CI and Read the Docs run
```
