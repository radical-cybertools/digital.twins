"""Streaming learner demo: sensor stream -> ROSE StreamingActiveLearner.

Mirrors rose_example, but the learner is retriggered per data window
instead of running once: sensor data arriving via ON_INPUT is fed into
the learner, every window of 5 items runs one train/active/criterion
iteration, and each time the criterion is met the model is published.

Start local_broker.py first, then run this script.
"""

import asyncio
import logging
import os
import random
import sys
from concurrent.futures import ProcessPoolExecutor

from radical.asyncflow import WorkflowEngine
from radical.asyncflow.logging import init_default_logger
from rhapsody.backends import ConcurrentExecutionBackend

from rose.al.streaming_learner import StreamingActiveLearner
from rose.metrics import MEAN_SQUARED_ERROR_MSE

from digitaltwin.components import *
from digitaltwin.runtime import DTRuntime, RuntimeAPI
from digitaltwin.streaming import connect_stream_client

logger = logging.getLogger(__name__)


SENSOR_DTYPE = DataType(name="sensor_data")


class StreamingInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # learn on windows of 5 sensor readings; drop backlog (latest wins)
        self.learner = StreamingActiveLearner(flow, batch_size=5, max_wait=2.0, conflate=True)
        self._code_path = f"{sys.executable} {os.getcwd()}"

        @self.learner.training_task
        async def training(window, *args, task_description={"shell": True}):
            values = " ".join(str(v) for v in window)
            return f"{self._code_path}/train.py {values}"

        @self.learner.active_learn_task
        async def active_learn(*args, task_description={"shell": True}):
            return f"{self._code_path}/active.py"

        @self.learner.as_stop_criterion(metric_name=MEAN_SQUARED_ERROR_MSE, threshold=0.08)
        async def check_mse(*args, task_description={"shell": True}):
            return f"{self._code_path}/check_mse.py"

        @self.flow.function_task
        async def inference_task(data: TypedData, model_info=""):
            print(f"Run inference on: {data.dtype}, {data.data}: kwargs: {model_info}")

        self.inference_task = inference_task

    async def on_input(self, data: TypedData):
        await self.learner.feed(data.data)

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.set_inference_task(self.inference_task)
        runtime.subscribe_to_topic(RuntimeAPI.ON_INPUT, self.on_input)

        # publish a bootstrap model: the DT pipeline gates each input on a
        # published model, so without this no stream data ever arrives
        runtime.publish_new_model({"model_info": "bootstrap"})

        # criterion met => model is good enough to publish; loop continues
        self.learner.on_model_ready(
            lambda state: runtime.publish_new_model(
                {"model_info": "model.json"}, {"mse": state.metric_value}
            )
        )

        async for state in self.learner.start():
            print(
                f"Window {state.iteration} ({state.window_size} items): "
                f"mse={state.metric_value:.4f} publish={state.should_stop}"
            )


class SensorTask(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data):
        for _ in range(100):
            await asyncio.sleep(0.3)
            await runtime.stream.publish(SENSOR_DTYPE, message=random.uniform(0, 1))


if __name__ == "__main__":

    async def main():
        init_default_logger(logging.INFO)
        logging.getLogger("radical.asyncflow").setLevel(logging.WARNING)
        logging.getLogger("rhapsody").setLevel(logging.WARNING)

        exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
        flow = await WorkflowEngine.create(backend=exe)

        pubsub_client = await connect_stream_client("rose-streaming")

        runtime = DTRuntime(flow, pubsub_client)

        sensor = SensorTask(flow)
        investigator = StreamingInvestigator(flow)

        runtime.add_task(sensor, TRUTHY, SENSOR_DTYPE, is_persistent=True)
        runtime.add_investigator(investigator, SENSOR_DTYPE, NULL_DTYPE)
        runtime.print_graph()
        runtime.start()

        await asyncio.sleep(30)
        investigator.learner.stop()
        await runtime.stop()
        await flow.shutdown()

    asyncio.run(main())
