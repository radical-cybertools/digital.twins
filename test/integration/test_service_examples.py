"""The documented service example runs against a live stack."""

import signal
import subprocess
import sys

from pathlib import Path

import pytest

from conftest import EXSITU_ENDPOINT, TASK_ENDPOINT, _child_env

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

RUN_TIMEOUT = 240.0


# above the job's --timeout=120, which also counts the endpoint fixture's
# start-up: the subprocess timeout must be the one that fires
@pytest.mark.timeout(300)
def test_the_surrogate_example_learns_on_the_service(stack, learning_endpoint):
    pytest.importorskip("rose.al.streaming_learner")

    proc = subprocess.Popen(
        [sys.executable, "run_service.py", "--timeout", "150"],
        cwd=EXAMPLES / "surrogate",
        env=_child_env(DT_INFERENCE_ENDPOINT=TASK_ENDPOINT,
                       DT_LEARNING_ENDPOINT=EXSITU_ENDPOINT),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )

    try:
        out, err = proc.communicate(timeout=RUN_TIMEOUT)
    except subprocess.TimeoutExpired:
        # SIGINT, not SIGKILL: the script's `finally` unregisters its
        # session, which would otherwise outlive it on the shared broker
        proc.send_signal(signal.SIGINT)
        out, err = proc.communicate(timeout=30)
        pytest.fail(f"run_service.py timed out:\n{out[-2000:]}{err[-2000:]}")

    assert proc.returncode == 0, out[-2000:] + err[-2000:]
    assert "surrogate is accurate" in out
