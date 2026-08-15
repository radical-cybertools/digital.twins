"""Ex-situ learning: a ROSE streaming learner inside a twin component.

`StreamingLearnerInvestigator` packages the wiring `test/rose_streaming`
spells out by hand -- a `StreamingActiveLearner` fed from `ON_INPUT`, a
bootstrap model published up front, `on_model_ready ->
publish_new_model`, and a learner whose lifetime is the twin's.

It is also the marker for **dual-engine injection**: the learner's
training / active-learning / criterion tasks run on the `'exsitu'` engine
(typically remote HPC hardware) while inference stays on the twin's
`'task'` engine.  The service detects this class by subclass check and
passes the second engine as `learn_flow`; locally the caller passes it
(or nothing -- one engine then serves both, which is what a
single-endpoint deployment does).

A subclass provides its learner tasks and its inference task::

    class Fit(StreamingLearnerInvestigator):

        def __init__(self, flow, learn_flow=None):
            super().__init__(flow, learn_flow, batch_size=8)

            # ex-situ, on `learn_flow`.  as_executable=False makes these
            # cloudpickled function tasks, which is what lets them run on
            # an endpoint that shares no filesystem with the service
            @self.learner.training_task(as_executable=False)
            async def training(window, *args):
                return {'slope': fit(window)}

            ...

            # in-situ, on `flow`
            @flow.function_task
            async def predict(in_data, slope=0.0):
                return in_data.data * slope

            self.inference_task = ...

This module needs ROSE (`pip install .[learn]`); nothing else in the
package imports it.
"""

import asyncio
import contextlib
import logging

from typing import Any, Callable, Optional

from radical.asyncflow import WorkflowEngine  # type: ignore
from rose.al.streaming_learner import StreamingActiveLearner  # type: ignore

from .components import ModelInvestigator, TypedData
from .runtime import RuntimeAPI

logger = logging.getLogger(__name__)

# how long twin teardown lets the learner leave its current window before
# the runtime cancels it outright
LEARNER_STOP_TIMEOUT = 5.0

# the three ROSE task slots a streaming learner drives
LEARNER_TASKS = ("training", "active_learn", "criterion")

# ROSE's own per-window bookkeeping -- state, but not model parameters
_ROSE_STATE_KEYS = ("window_size",)


class StreamingLearnerInvestigator(ModelInvestigator):
    """A `ModelInvestigator` with a ROSE `StreamingActiveLearner` inside.

    Every item the twin routes to this investigator is fed to the learner
    (`ON_INPUT`) *and* served by the inference task, so one stream drives
    both retraining and prediction.  Each window of `batch_size` items (or
    `max_wait` seconds' worth) runs one training / active-learning /
    criterion iteration on the `'exsitu'` engine; a met criterion is a
    publish gate, not a terminator -- it swaps the model the in-situ
    inference task runs with.
    """

    def __init__(
        self,
        flow: WorkflowEngine,
        learn_flow: Optional[WorkflowEngine] = None,
        batch_size: int = 5,
        max_wait: Optional[float] = 2.0,
        conflate: bool = True,
    ):
        super().__init__(flow)

        # Dual engine.  `learn_flow` is the 'exsitu' engine the service
        # injects; without one (local use, or a deployment that configured
        # no 'exsitu' engine) the twin's own engine serves both roles.
        self.learn_flow = flow if learn_flow is None else learn_flow

        # conflate: a stream faster than the learner drops its backlog
        # rather than growing it -- a days-long twin must not queue days
        # of sensor data
        self.learner = StreamingActiveLearner(
            self.learn_flow,
            batch_size=batch_size,
            max_wait=max_wait,
            conflate=conflate,
        )

        # set by the subclass; the in-situ half of the pair
        self.inference_task: Optional[Callable] = None

        self._started = False
        self._finished = asyncio.Event()

    # -- what subclasses shape ----------------------------------------------

    def bootstrap_model(self) -> tuple[dict, dict]:
        """The model published before any training has happened.

        Inference gates on a published model, so a learner that published
        only from `on_model_ready` would deadlock its twin on the very
        first input -- and nothing would ever reach the learner, since the
        stream feeds it through that same input.  Override to bootstrap
        with something better than the inference task's own defaults.
        """

        return {}, {}

    def published_model(self, state: Any) -> tuple[dict, dict]:
        """`(model_kwargs, accuracy_kwargs)` for a criterion-met window.

        Whatever the learner's tasks registered as state becomes the model
        -- a training task returning a dict has every key of it registered
        -- and those kwargs are what the inference task is called with.
        ROSE's own per-window bookkeeping is dropped.
        """

        model = {
            key: value
            for key, value in state.state.items()
            if key not in _ROSE_STATE_KEYS
        }

        return model, {"metric": state.metric_value}

    def on_window(self, state: Any) -> None:
        """Called once per learning window.  Default: one log line."""

        logger.info(
            "window %s (%s items): %s=%s published=%s",
            state.iteration,
            state.window_size,
            state.metric_name,
            state.metric_value,
            state.should_stop,
        )

    # -- the wiring ---------------------------------------------------------

    async def main_loop(self, runtime: RuntimeAPI):
        if self.inference_task is None:
            raise ValueError(
                f"{type(self).__name__} must set self.inference_task -- the"
                " in-situ inference, on the twin's 'task' engine"
            )

        self._warn_local_learner_tasks()

        runtime.set_inference_task(self.inference_task)
        runtime.subscribe_to_topic(RuntimeAPI.ON_INPUT, self._feed)
        runtime.publish_new_model(*self.bootstrap_model())

        # criterion met => this model is worth serving.  In streaming mode
        # the criterion is a publish gate and the loop keeps running.
        self.learner.on_model_ready(
            lambda state: runtime.publish_new_model(*self.published_model(state))
        )

        self._started = True

        try:
            async for state in self.learner.start():
                self.on_window(state)

        finally:
            # the failure path too: no learner outlives its twin
            self.learner.stop()
            self._finished.set()

    async def _feed(self, in_data: TypedData) -> None:
        """`ON_INPUT`: everything the twin sees also feeds the learner."""

        await self.learner.feed(in_data.data)

    async def _on_stop(self) -> None:
        """Wind the learner down before the runtime cancels the main loop.

        `learner.stop()` unblocks the window collector, so the loop leaves
        its `async for` and ROSE's generator runs its own cleanup (it
        cancels the source pumps it owns).  A bare cancellation would
        abandon that generator mid-window instead.  Bounded: a learner
        parked in a remote training task is cancelled with everything
        else, a moment later.
        """

        if not self._started:
            return

        self.learner.stop()

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._finished.wait(), LEARNER_STOP_TIMEOUT)

    def _warn_local_learner_tasks(self) -> None:
        """Warn about learner tasks that cannot leave this host.

        ROSE registers tasks as *executables* by default: the task body
        returns a command line, which only runs where that command exists
        under that path.  The `'exsitu'` engine points at other hardware,
        so learner tasks belong on the cloudpickle path -- registered with
        `as_executable=False` they travel as function tasks, and the
        backend's Python-version guard covers the rest.
        """

        local = [
            name
            for name in LEARNER_TASKS
            if (getattr(self.learner, f"{name}_function", None) or {}).get(
                "as_executable"
            )
        ]

        if local:
            logger.warning(
                "%s registered %s as executable task(s): a shell command with"
                " local paths does not survive a remote 'exsitu' endpoint."
                " Register them with as_executable=False.",
                type(self).__name__,
                ", ".join(local),
            )
