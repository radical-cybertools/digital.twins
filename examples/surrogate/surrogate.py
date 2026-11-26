"""The surrogate: a polynomial fit, retrained online from the stream.

Every reading the twin receives does two things:

- it is answered by the inference task with the current model, and
- it is fed to a ROSE streaming learner.  Each window of `batch_size`
  readings runs one learning iteration: label the window with the
  expensive simulation, fit, and score the fit.  A fit that beats the
  criterion is published and the next prediction uses it.

To use your own model, change the three learner tasks and the inference
task.  Keep the model small and JSON-friendly (lists of numbers): it is
handed to the inference task as keyword arguments and, on the service,
crosses the network with every window.
"""

import math

import numpy as np

from radical.doppelganger import TypedData
from radical.doppelganger.learn import StreamingLearnerInvestigator

from dtypes import PREDICTION
from physics import simulate

# polynomial degree of the surrogate
DEGREE = 9

# how much of the previous window's fit a new window keeps (warm start)
MEMORY = 0.7

# points the criterion validates against the noise-free simulation
HOLDOUT = [i * 2 * math.pi / 50 for i in range(50)]

# validation error below which a fit is good enough to serve
PUBLISH_RMSE = 0.06


def rmse(coeffs: list, xs: list) -> float:
    """Error of the polynomial `coeffs` against the simulation on `xs`."""

    errors = [(np.polyval(coeffs, x) - simulate(x, noise=0.0)) ** 2 for x in xs]

    return math.sqrt(sum(errors) / len(errors))


class Surrogate(StreamingLearnerInvestigator):

    def __init__(self, flow, learn_backend=None, batch_size: int = 64):
        super().__init__(flow, learn_backend, batch_size=batch_size,
                         max_wait=5.0)

        # The criterion task gets no input from the learner loop, so the
        # model it scores travels with it: `latest` mirrors the learner's
        # state and is captured by value.
        latest: dict = {}
        self.learner.on_state_update(latest.__setitem__)

        # --8<-- [start:learning]
        # -- the learning role ------------------------------------------
        # `as_executable=False` makes these Python function tasks.  They
        # can then run on a remote endpoint that shares no files with you.

        @self.learner.training_task(as_executable=False)
        async def training(window, previous=None, *args):
            xs = [float(x) for x in window]

            # a partial window (flushed after max_wait) can be too small
            # for the fit: keep the previous model
            if len(xs) <= DEGREE:
                return previous if isinstance(previous, dict) else {"coeffs": []}

            ys = [simulate(x) for x in xs]          # the expensive part
            coeffs = np.polyfit(xs, ys, DEGREE)

            if isinstance(previous, dict) and previous.get("coeffs"):
                coeffs = MEMORY * np.asarray(previous["coeffs"]) \
                       + (1 - MEMORY) * coeffs

            return {"coeffs": coeffs.tolist()}

        @self.learner.active_learn_task(as_executable=False)
        async def active_learn(model, *args):
            # a real one picks the next points to simulate; this one hands
            # the model on as the next window's warm start
            return model

        @self.learner.as_stop_criterion(metric_name="rmse",
                                        threshold=PUBLISH_RMSE, operator="<",
                                        as_executable=False)
        async def criterion(*args, model=latest):
            coeffs = model.get("coeffs")
            return rmse(coeffs, HOLDOUT) if coeffs else float("inf")

        # --8<-- [end:learning]
        # --8<-- [start:inference]
        # -- the inference role -----------------------------------------
        # Called once per reading with the published model as kwargs.

        @flow.function_task
        async def predict(x: float, coeffs=()):
            return float(np.polyval(coeffs, x)) if len(coeffs) else 0.0

        async def infer(in_data: TypedData, coeffs=()):
            return TypedData(PREDICTION, await predict(in_data.data, coeffs))

        self.inference_task = infer
        # --8<-- [end:inference]

    def bootstrap_model(self):
        """What the twin serves before the first fit is published."""

        return {"coeffs": []}, {}
