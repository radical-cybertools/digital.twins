"""The expensive model the surrogate replaces.

Replace `simulate` with your own simulation, solver or instrument.  In
this example it is a cheap analytic function with measurement noise, so
the whole twin runs on a laptop in well under a minute.
"""

import math
import random

NOISE = 0.05


def simulate(x: float, noise: float = NOISE) -> float:
    """The ground truth at `x`, with Gaussian noise of width `noise`."""

    value = math.sin(x) + 0.3 * math.sin(3 * x)

    return value + random.gauss(0.0, noise) if noise else value
