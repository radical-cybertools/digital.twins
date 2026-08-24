"""The second twin: a ROSE streaming learner, retraining ex-situ.

Two engines, two endpoints.  The learner's training windows go to the
`learning` backend; the inference it serves rides `inference`.  Both halves
report which endpoint they ran on, so the claim is checkable on screen
rather than asserted in prose.

Paced so the convergence bar in the dashboard moves during the
narration instead of snapping to converged on the first window.
"""

import os

from digitaltwin.components import DataType, TypedData
from digitaltwin.learn import StreamingLearnerInvestigator

from dtypes import INFERENCE_DTYPE, SENSOR_DTYPE

# the calibration the learner has to recover from the sensor stream
SLOPE = 10.0

# a window every BATCH_SIZE readings; at the sensor's 2.5s tick that is
# one training round roughly every 15s -- slow enough to point at
BATCH_SIZE = 6
MAX_WAIT = 30.0


def _tag() -> str:
    """Which endpoint is this task running on?  `os.environ` is the only
    channel a cloudpickled function body has for finding out."""

    return os.environ.get("DT_ENDPOINT_TAG", "?")


class DriftingLearner(StreamingLearnerInvestigator):
    def __init__(self, flow, learn_backend=None):
        super().__init__(flow, learn_backend, batch_size=BATCH_SIZE,
                         max_wait=MAX_WAIT)

        # the criterion task takes no dependency, so the model it scores
        # has to travel with it: this mirror is filled service-side from
        # each training result and cloudpickled on every submission
        latest: dict = {}
        self.learner.on_state_update(latest.__setitem__)

        # -- learning role: the label rides registration ---------------------

        @self.learner.training_task(as_executable=False)
        async def training(window, *args):
            # labelling the window stands in for the simulation a real
            # ex-situ learner would run out here
            xs = [float(x) for x in window]
            ys = [SLOPE * x for x in xs]
            den = sum(x * x for x in xs) or 1.0

            return {
                "slope": sum(x * y for x, y in zip(xs, ys)) / den,
                "trained_on": _tag(),
            }

        @self.learner.active_learn_task(as_executable=False)
        async def active_learn(model, *args):
            return len(model)

        @self.learner.as_stop_criterion(
            metric_name="fit_error",
            threshold=1e-6,
            operator="<",
            as_executable=False,
        )
        async def criterion(*args, model=latest):
            error = model.get("slope", 0.0) - SLOPE

            return error * error

        # -- in-situ, on `flow` ---------------------------------------------

        @flow.function_task
        async def predict(in_data: TypedData, slope=0.0, trained_on=""):
            return {
                "value": slope * in_data.data,
                "served_by": _tag(),
                "trained_on": trained_on,
            }

        async def infer(in_data: TypedData, slope=0.0, trained_on=""):
            return TypedData(INFERENCE_DTYPE,
                             await predict(in_data, slope=slope,
                                           trained_on=trained_on))

        self.inference_task = infer

    def bootstrap_model(self) -> tuple:
        """Nothing learned yet: every reading predicts zero."""

        return {"slope": 0.0}, {}
