"""The documented service example runs against a live stack."""

import subprocess
import sys

from pathlib import Path

import pytest

from conftest import EXSITU_ENDPOINT, TASK_ENDPOINT, _child_env

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


# above the job's --timeout=120, which also counts the endpoint fixture's
# start-up: the subprocess timeout must be the one that fires
@pytest.mark.timeout(300)
def test_the_surrogate_example_learns_on_the_service(stack, learning_endpoint):
    pytest.importorskip("rose.al.streaming_learner")

    result = subprocess.run(
        [sys.executable, "run_service.py", "--timeout", "150"],
        cwd=EXAMPLES / "surrogate",
        env=_child_env(DT_INFERENCE_ENDPOINT=TASK_ENDPOINT,
                       DT_LEARNING_ENDPOINT=EXSITU_ENDPOINT),
        capture_output=True, text=True, timeout=240,
    )

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "surrogate is accurate" in result.stdout
