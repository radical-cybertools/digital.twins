import asyncio
import os
import sys

from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

from rose.al.active_learner import SequentialActiveLearner
from rose.metrics import MEAN_SQUARED_ERROR_MSE

from concurrent.futures import ProcessPoolExecutor

from digitaltwin.components import *
from digitaltwin.runtime import DTRuntime, RuntimeAPI
from digitaltwin.streaming import PubSubClient, connect_stream_client

from radical.asyncflow.logging import init_default_logger

import logging

logger = logging.getLogger(__name__)


# Globals:


# = LocalBackend()
# Create the data types

SENSOR_DTYPE = DataType(name="sensor_data")


class MyInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # Learners
        self.acl = SequentialActiveLearner(self.flow)
        self._code_path = f"{sys.executable} {os.getcwd()}"

        # Register tasks

        # Learning tasks..............

        @self.acl.simulation_task
        async def simulation(*args, task_description={"shell": True}):
            return f"{self._code_path}/sim.py"

        @self.acl.training_task
        async def training(*args, task_description={"shell": True}):
            return f"{self._code_path}/train.py"

        @self.acl.active_learn_task
        async def active_learn(*args, task_description={"shell": True}):
            return f"{self._code_path}/active.py"

        @self.acl.as_stop_criterion(metric_name=MEAN_SQUARED_ERROR_MSE, threshold=0.1)
        async def check_mse(*args, task_description={"shell": True}):
            return f"{self._code_path}/check_mse.py"

        # inference task
        @self.flow.function_task
        async def inference_task(data: TypedData, model_info=""):
            print(f"Run inference on: {data.dtype}, {data.data}: kwargs: {model_info}")

        self.inference_task = inference_task

    # Callbacks .................

    # also supports as flow block
    async def on_input(self, data: TypedData):
        print(f"Received data: {data.data}")

    async def main_loop(self, runtime: RuntimeAPI):
        # call runtime ops
        runtime.set_inference_task(self.inference_task)
        runtime.subscribe_to_topic(RuntimeAPI.ON_INPUT, self.on_input)

        # Start the active learning process
        # Define and register the simulation task

        # Start the active learning process
        async for state in self.acl.start():
            print(f"Iteration {state.iteration}: metric={state.metric_value}")

        # publish final output
        model_fname = "sim_output.pkl"
        kwargs = {"model_info": model_fname}
        runtime.publish_new_model(kwargs)


class MyPersistentTask(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data):
        output_dtype = SENSOR_DTYPE
        ps = await runtime.stream_config.connect()

        for i in range(100):
            await asyncio.sleep(1)
            logger.debug(f"Publish message with dtype: {output_dtype}")
            await ps.publish(output_dtype, message="Hello!")


if __name__ == "__main__":

    async def main():
        init_default_logger(logging.INFO)
        exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
        flow = await WorkflowEngine.create(backend=exe)

        pubsub_client = await connect_stream_client("rose-example")

        runtime = DTRuntime(flow, pubsub_client)

        # # define the tasks / investigators
        sensor_task = MyPersistentTask(flow)
        investigator = MyInvestigator(flow)

        # # create the graph
        runtime.add_task(sensor_task, TRUTHY, SENSOR_DTYPE, is_persistent=True)
        runtime.add_investigator(investigator, SENSOR_DTYPE, NULL_DTYPE)
        runtime.print_graph()
        runtime.start()

        # let it run....
        await asyncio.sleep(30)
        await flow.shutdown()

    asyncio.run(main())
