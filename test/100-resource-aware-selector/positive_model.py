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


class PositiveModel(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning.... just inference for now.
        # inference changes given the args passed in.

        @self.flow.function_task
        async def do_inference(in_data: TypedData, offset=1):
            return TypedData(INFERENCE_DTYPE, offset - in_data.data)

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)

        offset = 2
        while True:
            await asyncio.sleep(5)
            runtime.publish_new_model({"offset": offset})
            offset += 1
