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
        self.offset = 1
        self.to_publish = asyncio.Event()

        # no learning.... just inference for now.
        # inference changes given the args passed in.

        @self.flow.function_task
        async def do_inference(in_data: TypedData, offset=1):
            return TypedData(INFERENCE_DTYPE, offset - in_data.data)

        self.inference_task = do_inference

    async def on_input(self, in_data: TypedData):
        if in_data.data > 0.5:
            print("Input is bigger... publish a new model")
            # update offset
            self.offset += 1
            self.to_publish.set()

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model()
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.on_input)

        while True:
            await self.to_publish.wait()
            runtime.publish_new_model({"offset": self.offset})
            self.to_publish.clear()
