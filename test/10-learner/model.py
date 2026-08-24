"""The ex-situ learner: a calibration refitted from the live stream.

The twin serves `prediction = slope * reading + intercept` in-situ while
a ROSE streaming learner refits `(slope, intercept)` ex-situ from the
same stream.  Two engines, stated explicitly:

- the **learner** tasks (training / active learning / criterion) run on
  the `'learning'` backend -- typically remote HPC hardware.  They are
  registered `as_executable=False`, which makes them *cloudpickled
  function tasks*: a shell command with local paths would not survive an
  endpoint that shares no filesystem with the service.
- the **inference** task rides the twin's `'inference'` backend, co-located
  with the service, because it sits in the per-reading critical path.

`StreamingLearnerInvestigator` is what tells the service to inject both:
it takes the learning label as `learn_backend`, and passes the ordinary
`flow` to the inference task.
"""

import logging
import math
import random

from digitaltwin.components import TypedData
from digitaltwin.learn import StreamingLearnerInvestigator

from dtypes import PREDICTION_DTYPE

logger = logging.getLogger(__name__)

# the calibration the learner has to discover.  It lives in the training
# task's world (a stand-in for the reference instrument / simulation a
# real twin would run ex-situ), never in the inference task's.
TRUE_SLOPE = 2.5
TRUE_INTERCEPT = 1.0
NOISE = 0.4

# how much of the previous window's model a new one keeps.  ROSE feeds
# the last active-learning result back in as a training dependency; that
# is the warm start, and it is what makes the fit converge across
# windows instead of hopping around with the noise.
MEMORY = 0.6

# readings the criterion scores the model on, and the error at which the
# model is good enough to serve
HOLDOUT = [0.0, 2.5, 5.0, 7.5, 10.0]
PUBLISH_RMSE = 0.25


def fit(xs: list, ys: list) -> tuple:
    """Ordinary least squares through `(xs, ys)`."""

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var = sum((x - mean_x) ** 2 for x in xs)

    slope = cov / var if var else 0.0

    return slope, mean_y - slope * mean_x


def rmse(slope: float, intercept: float, xs: list) -> float:
    """Error of a calibration against the truth, on `xs`."""

    errors = [
        (slope * x + intercept - (TRUE_SLOPE * x + TRUE_INTERCEPT)) ** 2 for x in xs
    ]

    return math.sqrt(sum(errors) / len(errors))


class CalibrationLearner(StreamingLearnerInvestigator):
    """Refits the sensor calibration from every window of readings."""

    def __init__(self, flow, learn_backend=None, batch_size: int = 8):
        super().__init__(flow, learn_backend, batch_size=batch_size, max_wait=5.0)

        # The criterion task takes no dependency, so the model it scores
        # has to travel *with* it: ROSE registers a task's returned dict
        # as state, this mirror collects it service-side, and it is
        # cloudpickled by value on every submission.  On a remote
        # endpoint there is no `model.json` to read.
        latest: dict = {}
        self.learner.on_state_update(latest.__setitem__)

        # -- learning role: the label rides registration ---------------------

        @self.learner.training_task(as_executable=False)
        async def training(window, previous=None, *args):
            # labelling the window is the expensive, ex-situ half: this
            # stands in for the reference instrument or the simulation
            xs = [float(x) for x in window]
            ys = [TRUE_SLOPE * x + TRUE_INTERCEPT + random.gauss(0, NOISE)
                  for x in xs]

            slope, intercept = fit(xs, ys)

            # warm start: `previous` is the last window's model, handed
            # back by the active-learning task
            if isinstance(previous, dict):
                slope = MEMORY * previous["slope"] + (1 - MEMORY) * slope
                intercept = MEMORY * previous["intercept"] + (1 - MEMORY) * intercept

            return {"slope": slope, "intercept": intercept}

        @self.learner.active_learn_task(as_executable=False)
        async def active_learn(model, *args):
            # a real one picks the next samples to label; this one just
            # carries the model forward as the next window's warm start
            return model

        @self.learner.as_stop_criterion(
            metric_name="rmse",
            threshold=PUBLISH_RMSE,
            operator="<",
            as_executable=False,
        )
        async def criterion(*args, model=latest, holdout=HOLDOUT):
            return rmse(model.get("slope", 0.0), model.get("intercept", 0.0),
                        holdout)

        # -- in-situ, on `flow` ---------------------------------------------

        @flow.function_task
        async def predict(in_data: TypedData, slope=0.0, intercept=0.0):
            return slope * in_data.data + intercept

        async def infer(in_data: TypedData, slope=0.0, intercept=0.0):
            value = await predict(in_data, slope=slope, intercept=intercept)
            return TypedData(PREDICTION_DTYPE, value)

        self.inference_task = infer

    def bootstrap_model(self) -> tuple:
        """An uncalibrated sensor: everything reads zero until the first
        window has been learned."""

        return {"slope": 0.0, "intercept": 0.0}, {}
