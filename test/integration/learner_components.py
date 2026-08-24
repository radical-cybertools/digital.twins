"""The dual-engine twin components the M2 integration tests ship.

Cloudpickled by value (the service has no copy of this module), so it
must stay importable on its own -- no test imports, no fixtures.

Separate from `twin_components` because importing it needs ROSE: a
service without the `learn` extra still hosts every M1 twin.
"""

import os

from digitaltwin.components import DataType, TypedData
from digitaltwin.learn import StreamingLearnerInvestigator

SENSOR_DTYPE = DataType("sensor")
INFERENCE_DTYPE = DataType("inference")

# the calibration the learner has to recover.  `CountingSensor` streams
# 0, 1, 2, ... so a least-squares fit through the origin lands on it
# exactly -- no tolerance games in the assertions.
SLOPE = 10.0

# batch_size items per window, or `max_wait` seconds' worth
BATCH_SIZE = 4
MAX_WAIT = 10.0


def _tag() -> str:
    """Which endpoint is this task running on?

    `os.environ` is the only channel a cloudpickled function body has for
    finding that out; the fixtures stamp every endpoint with its name.
    """

    return os.environ.get("DT_TEST_ENDPOINT_TAG", "?")


class LinearLearner(StreamingLearnerInvestigator):
    """Fits `y = slope * x` ex-situ and serves it in-situ.

    Both halves report the endpoint they ran on, so a test can assert
    that the learner tasks and the inference really went to different
    engines.
    """

    def __init__(self, flow, learn_flow=None):
        super().__init__(flow, learn_flow, batch_size=BATCH_SIZE,
                         max_wait=MAX_WAIT)

        # the criterion task takes no dependency, so the model it scores
        # travels with it: this mirror is filled service-side from each
        # training result and cloudpickled by value on every submission
        latest: dict = {}
        self.learner.on_state_update(latest.__setitem__)

        # -- ex-situ, on `learn_flow` ---------------------------------------

        @self.learner.training_task(as_executable=False)
        async def training(window, *args):
            # labelling the window stands in for the simulation an
            # ex-situ learner would run
            xs = [float(x) for x in window]
            ys = [SLOPE * x for x in xs]
            den = sum(x * x for x in xs) or 1.0

            return {
                "slope": sum(x * y for x, y in zip(xs, ys)) / den,
                "trained_on": _tag(),
            }

        @self.learner.active_learn_task(as_executable=False)
        async def active_learn(model, *args):
            # a non-dict result: nothing here belongs in the model
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
            # a dict return value: rich results round-trip through ORBIT
            return {
                "value": slope * in_data.data,
                "served_by": _tag(),
                "trained_on": trained_on,
            }

        async def infer(in_data: TypedData, slope=0.0, trained_on=""):
            answer = await predict(in_data, slope=slope, trained_on=trained_on)
            return TypedData(INFERENCE_DTYPE, answer)

        self.inference_task = infer

    def bootstrap_model(self) -> tuple:
        """Nothing learned yet: every reading predicts zero."""

        return {"slope": 0.0}, {}
