# Install

Doppelganger needs Python 3.11 or newer.  Use one virtual environment per
project.

## From a release

```sh
python3 -m venv ve && . ve/bin/activate
pip install "radical.doppelganger[learn]"            # build and run twins locally
pip install "radical.doppelganger[service,learn]"    # also talk to, or host, the service
```

The extras:

| Extra | Adds | Needed for |
|---|---|---|
| (none) | the framework: components, runtime, streams | local twins without online learning |
| `learn` | ROSE | `StreamingLearnerInvestigator`, online training |
| `service` | radical.orbit, rhapsody telemetry | the `dt` service plugin and its client |
| `test` | pytest | running the test suite |

## Until the stack is released

The first PyPI releases are in preparation.  Until rhapsody,
radical.asyncflow and ROSE are released with it, install the exact
versions the project tests with, in this order:

<!-- stack-pins -->

These pins come from `deploy/install.sh`, which is also what deployments
use.  Two traps they avoid:

- PyPI's `rose` is an unrelated package.  `pip install rose` installs it
  without complaint, and the learner then fails on `import rose.al`.
- PyPI's `rhapsody-py` 0.4.0 lacks the ORBIT execution backend the
  service runs on.

## Check the install

```sh
python -c "import radical.doppelganger as dg; print(dg.__file__)"
python -c "from radical.doppelganger.service.wire import version_stamp; print(version_stamp())"
```

The second line prints the versions the service compares.  For the
service, every host (client, broker, endpoints) must print the same
`python`, `cloudpickle` and `radical.doppelganger` values.

## Upgrading from `digitaltwin`

The package was called `digitaltwin` before its first release.  In an
environment that has it, uninstall it first:

```sh
pip uninstall digitaltwin
```

Otherwise both packages register the `dt` ORBIT plugin.  Move client and
service to the new name together: a renamed client talking to an old
service is refused with `client did not report its digitaltwin version`.
