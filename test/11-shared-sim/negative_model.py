import asyncio
import os
import sys

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class NegativeModel(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning.... just inference for now.
        # inference changes given the args passed in.

        @self.flow.function_task
        async def do_inference(in_data: TypedData, offset=1):
            return TypedData(INFERENCE_DTYPE, -1 * (offset - in_data.data))

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)

        offset = 0
        while True:
            # run a sim - direct call.
            offset += await runtime.call_shared_subtask(SHARED_SIM, offset)
            runtime.publish_new_model({"offset": offset})
            await asyncio.sleep(5)
