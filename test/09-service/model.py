import asyncio
import logging
import time

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI

from dtypes import *

logger = logging.getLogger(__name__)


class MyModel(ModelInvestigator):
    """No learning -- just inference, whose result changes with the
    published model arguments.

    The compute runs on the engine (and therefore on a rhapsody
    endpoint); the `TypedData` wrapping happens here, in the service.
    Function task *arguments* are cloudpickled, but return values only
    survive the ORBIT rhapsody plugin if they are JSON-safe or bytes --
    so tasks return plain values.
    """

    def __init__(self, flow: WorkflowEngine, *args, **kwargs):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task(backend="learning")
        async def compute():
            print("\n RUNNING SIM ............ \n")
            time.sleep(5)
            return

        self.compute = compute

        @self.flow.function_task(backend="inference")
        async def do_inference(in_data: TypedData, offset=1):
            print("\n RUNNING INFERENCE............ \n")
            return TypedData(INFERENCE_DTYPE, offset - in_data.data)

        self.do_inference = do_inference

    async def main_loop(self, runtime: RuntimeAPI):

        runtime.set_inference_task(self.do_inference)

        offset = 2
        while True:
            runtime.publish_new_model({"offset": offset})
            offset += 1
            # simulate a long sim
            await self.compute()
