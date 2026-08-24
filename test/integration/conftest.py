"""A live DTaaS stack for the integration tests.

Session-scoped fixtures bring up, on loopback:

- an ORBIT broker hosting the `dt` plugin (`--plugins default,dt`),
- a co-located rhapsody endpoint with `backends=['concurrent']` and the
  notification window at 0 (P2 -- otherwise every sequential task pays
  250 ms),
- a second rhapsody endpoint standing in for remote HPC hardware, which
  is where the `'exsitu'` engine sends learner tasks,
- a consumer runtime the tests get `DTClient`s from.

Plus a *second, independent* stack on the next port whose `dt` plugin
runs with `DT_STREAM_BACKEND=orbit` (M3): same shape, but the twins'
streams ride ORBIT eventing and no ZMQ broker is started anywhere.  It is
a separate deployment because the backend is a deployment-time choice --
which is exactly what the M3 tests assert.

Every endpoint carries a `DT_TEST_ENDPOINT_TAG` in its environment, so a
task can report where it ran -- which is how the dual-engine tests prove
that learning and inference really landed on different endpoints.

Everything is skipped when the broker cannot be started (no certs, no
token, port taken), so the suite stays runnable without a deployment.
"""

import contextlib
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid

from pathlib import Path
from typing import NamedTuple

import pytest

try:
    import httpx

    from radical.orbit import EndpointRuntime
except ImportError:  # no ORBIT installed: there is nothing here to run
    collect_ignore_glob = ["*"]

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

BROKER_HOST = "127.0.0.1"
BROKER_PORT = int(os.environ.get("DT_TEST_BROKER_PORT", "8031"))
BROKER_URL = f"https://{BROKER_HOST}:{BROKER_PORT}"

# the M3 stack: a `dt` deployment whose data plane is ORBIT eventing
ORBIT_BROKER_PORT = BROKER_PORT + 1
ORBIT_BROKER_URL = f"https://{BROKER_HOST}:{ORBIT_BROKER_PORT}"

TASK_ENDPOINT = "dt_test_task_ep"
EXSITU_ENDPOINT = "dt_test_exsitu_ep"  # stands in for remote HPC hardware
DOOMED_ENDPOINT = "dt_test_doomed_ep"  # started to be killed (R8)
DT_ENDPOINT = "dt_test_dt_ep"  # endpoint-hosted `dt`, for the smoke test
ORBIT_TASK_ENDPOINT = "dt_test_orbit_task_ep"  # on the M3 stack

STARTUP_TIMEOUT = 60.0
LOGS = Path(os.environ.get("DT_TEST_LOG_DIR", "/tmp")) / "dt-integration-logs"


def engines(**endpoints: str) -> dict:
    """Session config for the named engines, concurrent backend each."""

    return {
        "engines": {
            name: {"endpoint_name": endpoint, "backends": ["concurrent"]}
            for name, endpoint in endpoints.items()
        }
    }


# the single-engine wiring most tests use: the co-located endpoint only
ENGINES = engines(task=TASK_ENDPOINT)

# dual-engine wiring: learner tasks ex-situ, everything else co-located
ENGINES_DUAL = engines(task=TASK_ENDPOINT, exsitu=EXSITU_ENDPOINT)

# same, but with an ex-situ engine on an endpoint the test will kill
ENGINES_DOOMED = engines(task=TASK_ENDPOINT, exsitu=DOOMED_ENDPOINT)

# the M3 stack's single engine
ENGINES_ORBIT = engines(task=ORBIT_TASK_ENDPOINT)


def _port_free(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((BROKER_HOST, port)) != 0


def _child_env(**extra: str) -> dict:
    """Environment for a broker / endpoint child process.

    `src` goes first on PYTHONPATH so the children run the working tree,
    not whatever `digitaltwin` happens to be installed.  Anything in
    `extra` wins -- that is how the M3 children get their own broker URL
    and `DT_STREAM_BACKEND`.
    """

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC), *filter(None, [env.get("PYTHONPATH")])]
    )
    env["RADICAL_ORBIT_BROKER_URL"] = BROKER_URL
    env.update(extra)

    return env


def _spawn(name: str, argv: list, **env: str) -> subprocess.Popen:
    """Start a child, logging to `LOGS/<name>.log`.

    The log handle rides on the process object so `_terminate` can close
    it -- these fixtures are session-scoped, but the pytest process must
    not accumulate descriptors either.
    """

    LOGS.mkdir(parents=True, exist_ok=True)
    log = (LOGS / f"{name}.log").open("w")

    try:
        proc = subprocess.Popen(
            argv, env=_child_env(**env), stdout=log, stderr=subprocess.STDOUT
        )
    except BaseException:
        log.close()
        raise

    proc._dt_log = log

    return proc


def _terminate(proc: subprocess.Popen, timeout: float = 15.0) -> None:
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(5)
    finally:
        log = getattr(proc, "_dt_log", None)
        if log is not None and not log.closed:
            log.close()


def _orbit_script(name: str) -> list:
    """Locate an ORBIT entry script (installed, or in a source checkout)."""

    import radical.orbit

    candidates = [
        Path(sys.executable).parent / name,  # this interpreter's env
        # a source checkout: .../site-packages/radical/orbit -> ../../../bin
        Path(radical.orbit.__file__).resolve().parents[3] / "bin" / name,
    ]
    for script in candidates:
        if script.exists():
            return [sys.executable, str(script)]

    installed = shutil.which(name)
    if installed:
        return [installed]

    pytest.skip(f"cannot locate {name}")


class Broker(NamedTuple):
    """The broker under test: where to reach it, and which process it is
    (tests assert against *this* broker's resources, never against
    whatever else on the host happens to look like a broker)."""

    url: str
    pid: int


@contextlib.contextmanager
def _dt_broker(label: str, port: int, url: str, **env: str):
    """An ORBIT broker on a loopback port, hosting `dt`, torn down on exit."""

    if not _port_free(port):
        pytest.skip(f"port {port} is busy")

    argv = _orbit_script("radical-orbit-broker.py") + [
        "--host", BROKER_HOST,
        "--port", str(port),
        "--plugins", "default,dt",
    ]
    proc = _spawn(label, argv, RADICAL_ORBIT_BROKER_URL=url, **env)

    try:
        _await_broker(label, url, proc)
        yield Broker(url, proc.pid)
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def broker():
    """An ORBIT broker on a non-default loopback port, hosting `dt`."""

    with _dt_broker("broker", BROKER_PORT, BROKER_URL) as running:
        yield running


@pytest.fixture(scope="session")
def orbit_broker():
    """The M3 deployment: the same broker with the ORBIT data plane.

    `DT_STREAM_BACKEND=orbit` is set on the broker process, because the
    transport is a property of the deployment -- no client and no session
    can ask for it.
    """

    with _dt_broker("orbit-broker", ORBIT_BROKER_PORT, ORBIT_BROKER_URL,
                    DT_STREAM_BACKEND="orbit") as running:
        yield running


def _await_broker(label: str, url: str, proc: subprocess.Popen) -> None:
    deadline = time.time() + STARTUP_TIMEOUT

    while time.time() < deadline:
        if proc.poll() is not None:
            pytest.skip(f"{label} exited early -- see {LOGS / label}.log")
        try:
            httpx.get(url + "/", verify=False, timeout=2)
            return
        except Exception:
            time.sleep(0.25)

    _terminate(proc)
    pytest.skip(f"{label} did not come up -- see {LOGS / label}.log")


@contextlib.contextmanager
def _rhapsody_endpoint(name: str, broker, **env: str):
    """A rhapsody endpoint, up and advertised, torn down on exit.

    `DT_TEST_ENDPOINT_TAG` is the endpoint's name to a task running on
    it: `os.environ` is the only channel a cloudpickled function body has
    for finding out where it landed.
    """

    argv = _orbit_script("radical-orbit-endpoint.py") + [
        "-n", name, "-u", broker.url, "-p", "default",
    ]
    proc = _spawn(
        name,
        argv,
        RADICAL_ORBIT_BROKER_URL=broker.url,
        RADICAL_ORBIT_RHAPSODY_BACKEND="concurrent",
        DT_TEST_ENDPOINT_TAG=name,
        **env,
    )

    try:
        _await_plugin(name, "rhapsody", proc, broker.url)
        yield proc
    finally:
        _terminate(proc)


@pytest.fixture(scope="session")
def task_endpoint(broker):
    """A co-located rhapsody endpoint: where the twins' tasks execute."""

    # notify window 0 (P2): every sequential in-situ prediction would
    # otherwise pay 250 ms
    with _rhapsody_endpoint(TASK_ENDPOINT, broker,
                            RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW="0"):
        yield TASK_ENDPOINT


@pytest.fixture(scope="session")
def exsitu_endpoint(broker):
    """A second rhapsody endpoint: where learner tasks execute.

    Distinct from `task_endpoint` on purpose -- that is the whole point
    of the `'exsitu'` engine.  It keeps the default notify window: 250 ms
    is noise under a training task.
    """

    with _rhapsody_endpoint(EXSITU_ENDPOINT, broker):
        yield EXSITU_ENDPOINT


@pytest.fixture
def doomed_endpoint(broker):
    """A disposable rhapsody endpoint the test is expected to kill (R8).

    Its own endpoint rather than a shared one: the R8 test asserts on
    what an endpoint *loss* does, and the rest of the suite still needs
    somewhere to run.
    """

    with _rhapsody_endpoint(DOOMED_ENDPOINT, broker) as proc:
        yield proc


@pytest.fixture(scope="session")
def dt_endpoint(broker):
    """An endpoint hosting the `dt` plugin itself (endpoint-hosted mode).

    It deliberately does *not* load rhapsody: its twins' tasks go to
    `task_endpoint`, exactly as in the broker-hosted deployment.
    """

    argv = _orbit_script("radical-orbit-endpoint.py") + [
        "-n", DT_ENDPOINT, "-u", broker.url, "-p", "dt",
    ]
    proc = _spawn(DT_ENDPOINT, argv)

    try:
        _await_plugin(DT_ENDPOINT, "dt", proc, BROKER_URL)
        yield DT_ENDPOINT
    finally:
        _terminate(proc)


def _await_plugin(endpoint: str, plugin: str, proc: subprocess.Popen,
                  broker_url: str = BROKER_URL) -> None:
    """Wait until `endpoint` advertises `plugin` in the broker topology."""

    runtime = EndpointRuntime(broker_url=broker_url)
    runtime.start(wait=True)

    try:
        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            if proc.poll() is not None:
                pytest.skip(f"{endpoint} exited -- see {LOGS / endpoint}.log")

            info = runtime.topology().get(endpoint) or {}
            if plugin in (info.get("plugins") or {}):
                return

            time.sleep(0.25)

    finally:
        runtime.stop()

    _terminate(proc)
    pytest.skip(f"{endpoint} never advertised {plugin!r}")


@pytest.fixture(scope="session")
def stack(broker, task_endpoint):
    """The full broker + endpoint stack; returns the broker URL."""

    return broker.url


@pytest.fixture(scope="session")
def broker_pid(broker):
    """The pid of the broker under test -- for resource assertions."""

    return broker.pid


@pytest.fixture
def runtime(stack):
    """A fresh consumer runtime -- one per test, like a real client."""

    rt = EndpointRuntime(broker_url=stack)
    rt.start(wait=True)
    try:
        yield rt
    finally:
        rt.stop()


@pytest.fixture
def dt_client(runtime):
    """Factory for `DTClient`s with an explicit engine configuration.

    Every session it hands out is closed with the test -- sessions are
    immortal, so nothing else would ever reclaim them.
    """

    clients = []

    def make(config: dict = ENGINES):
        client = runtime.get_plugin("broker", "dt", config=config)
        clients.append(client)
        return client

    try:
        yield make
    finally:
        for client in clients:
            _drop_session(client)


@pytest.fixture
def dt(dt_client):
    """A `DTClient` on a fresh single-engine session."""

    return dt_client()


def _drop_session(client) -> None:
    """Close every twin, then unregister -- sessions are immortal."""

    try:
        for twin in client.twin_list():
            client.twin_close(twin["twin_id"])
        client.unregister_session()
    except Exception as exc:  # a test may have closed it already
        print(f"session teardown: {exc}")


@pytest.fixture
def twin_id():
    """A fresh client-supplied twin uuid."""

    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# the M3 stack: the same shape, with the ORBIT data plane
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def orbit_task_endpoint(orbit_broker):
    """The M3 stack's co-located rhapsody endpoint."""

    with _rhapsody_endpoint(ORBIT_TASK_ENDPOINT, orbit_broker,
                            RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW="0"):
        yield ORBIT_TASK_ENDPOINT


@pytest.fixture(scope="session")
def orbit_stack(orbit_broker, orbit_task_endpoint):
    """The full M3 stack; returns its broker URL."""

    return orbit_broker.url


@pytest.fixture
def orbit_runtime(orbit_stack):
    """A consumer runtime on the M3 broker -- one per test."""

    rt = EndpointRuntime(broker_url=orbit_stack)
    rt.start(wait=True)
    try:
        yield rt
    finally:
        rt.stop()


@pytest.fixture
def orbit_dt(orbit_runtime):
    """A `DTClient` on a fresh session of the M3 stack."""

    client = orbit_runtime.get_plugin("broker", "dt", config=ENGINES_ORBIT)
    try:
        yield client
    finally:
        _drop_session(client)
