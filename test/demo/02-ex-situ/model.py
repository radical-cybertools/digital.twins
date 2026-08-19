import asyncio
import datetime
import os
import sys

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData
from digitaltwin.runtime import RuntimeAPI

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MyModel(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        self.to_update = asyncio.Event()

        f = open("model-inference.out", "w")
        f.write("Model Inference Task ========================= \n")
        f.close()

        f = open("model-learner.out", "w")
        f.write("Model Learner ========================= \n")
        f.close()

        # no learning.... just inference for now.

        # @self.flow.function_task
        async def do_inference(in_data: TypedData, model="", diff=100):
            f = open("model-inference.out", "a")
            print(f"Do inf: {in_data}")
            val = diff - in_data.data
            f.write(
                f"[{datetime.datetime.now()}] Received: {in_data.data}. Model: {model} Output: {val}\n"
            )
            f.close()
            return TypedData(INFERENCE_DTYPE, val)

        self.inference_task = do_inference

    async def sensor_callback(self, in_data):
        f = open("model-learner.out", "a")
        f.write(f"[{datetime.datetime.now()}] Learner received: {in_data.data} \n")
        f.close()

        if in_data.data % 10 == 0:
            self.to_update.set()

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.sensor_callback)
        runtime.set_inference_task(self.inference_task)

        diff = 100
        model = 1
        while True:
            await self.to_update.wait()
            f = open("model-learner.out", "a")
            f.write(f"[{datetime.datetime.now()}] Publish model: model_{model} \n")
            f.close()
            runtime.publish_new_model({"model": f"model_{model}", "diff": diff})
            self.to_update.clear()
            diff += 100
            model += 1
