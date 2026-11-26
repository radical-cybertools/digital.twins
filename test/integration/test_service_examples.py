"""The documented service example runs against a live stack."""

import signal
import subprocess
import sys

from pathlib import Path

import pytest

from conftest import EXSITU_ENDPOINT, STARTUP_TIMEOUT, TASK_ENDPOINT, _child_env

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

RUN_TIMEOUT = 240.0


def run_example(argv: list, cwd: Path, timeout: float, **kwargs):
    """As in test/unit/test_examples.py: on a hang, interrupt the script so
    its `finally` unregisters its session on the shared broker."""

    proc = subprocess.Popen([sys.executable, *argv], cwd=cwd, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            **kwargs)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.send_signal(signal.SIGINT)
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, err = proc.communicate()
        pytest.fail(f"{argv[0]} timed out:\n{out[-2000:]}{err[-2000:]}")

    return proc.returncode, out, err


# pytest-timeout also counts fixture start-up (the learning endpoint can
# take STARTUP_TIMEOUT) and the interrupt's grace period: leave room for
# both, so the subprocess timeout is the one that fires
@pytest.mark.timeout(RUN_TIMEOUT + STARTUP_TIMEOUT + 60)
def test_the_surrogate_example_learns_on_the_service(stack, learning_endpoint):
    pytest.importorskip("rose.al.streaming_learner")

    rc, out, err = run_example(
        ["run_service.py", "--timeout", "150"], EXAMPLES / "surrogate",
        RUN_TIMEOUT,
        env=_child_env(DT_INFERENCE_ENDPOINT=TASK_ENDPOINT,
                       DT_LEARNING_ENDPOINT=EXSITU_ENDPOINT))

    assert rc == 0, out[-2000:] + err[-2000:]
    assert "surrogate is accurate" in out
