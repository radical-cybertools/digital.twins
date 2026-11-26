import asyncio
import os
import sys

from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import ModelInvestigator, TypedData
from radical.doppelganger.runtime import RuntimeAPI

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MyModel(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning.... just inference for now.

        # @self.flow.function_task
        async def do_inference(in_data: TypedData):
            return TypedData(INFERENCE_DTYPE, in_data.data)

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model()
