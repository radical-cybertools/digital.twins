"""The documented examples run, end to end.

The docs include their code from `examples/`, so a passing run here is
what keeps the tutorials true.
"""

import subprocess
import sys

from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


# above the job's --timeout=120: the subprocess timeout must be the one that fires
@pytest.mark.timeout(200)
def test_the_surrogate_example_learns_locally():
    pytest.importorskip("rose.al.streaming_learner")

    result = subprocess.run(
        [sys.executable, "run_local.py", "--timeout", "90"],
        cwd=EXAMPLES / "surrogate",
        capture_output=True, text=True, timeout=150,
    )

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "surrogate is accurate" in result.stdout
