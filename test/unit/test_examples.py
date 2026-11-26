"""The documented examples run, end to end.

The docs include their code from `examples/`, so a passing run here is
what keeps the tutorials true.
"""

import signal
import subprocess
import sys

from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

RUN_TIMEOUT = 150.0


def run_example(argv: list, cwd: Path, timeout: float, **kwargs):
    """Run an example script; on a hang, interrupt it so its `finally`
    tears down what it started (the broker child, a service session)."""

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


# above the job's --timeout=120: the subprocess timeout must be the one
# that fires, with room for the interrupt's grace period
@pytest.mark.timeout(RUN_TIMEOUT + 60)
def test_the_surrogate_example_learns_locally():
    pytest.importorskip("rose.al.streaming_learner")

    rc, out, err = run_example(["run_local.py", "--timeout", "90"],
                               EXAMPLES / "surrogate", RUN_TIMEOUT)

    assert rc == 0, out[-2000:] + err[-2000:]
    assert "surrogate is accurate" in out
