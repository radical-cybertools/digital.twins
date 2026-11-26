import asyncio
from dataclasses import dataclass
import datetime
import os
import sys

from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import ModelInvestigator, TypedData
from radical.doppelganger.runtime import RuntimeAPI

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


@dataclass
class Dart:
    x: float
    y: float


class MonteCarlo(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning.... just inference for now.
        # inference changes given the args passed in.

        f = open("monte-inference.out", "w")
        f.write("MONTE Model Inference Task ========================= \n")
        f.close()

        @self.flow.function_task
        async def do_inference(in_data: TypedData, pi_val=0):
            f = open("monte-inference.out", "a")
            f.write(
                f"[{datetime.datetime.now()}] Received: {in_data.data}. Sending: {pi_val}\n"
            )
            f.close()
            return TypedData(PI_DTYPE, pi_val)

        self.inference_task = do_inference

        self.series_n = 1
        self.sum = 3
        self.sim_trigger = asyncio.Event()

        @self.flow.function_task
        async def throw_dart():
            x = random.random() * 2 - 1  # -1 to 1
            y = random.random() * 2 - 1
            return Dart(x, y)

        self.throw_dart = throw_dart

        @self.flow.function_task
        async def train(in_circle, total, incoming_dart: Dart):
            if incoming_dart.x**2 + incoming_dart.y**2 <= 1:
                in_circle += 1
            total += 1
            return in_circle, total, 4 * (in_circle / total)

        self.train = train

    async def on_input(self, in_data: TypedData):
        f = open("monte-learner.out", "a")
        f.write(f"[{datetime.datetime.now()}] MONTE received input: {in_data.data} \n")
        f.close()
        self.sim_trigger.set()

    async def main_loop(self, runtime: RuntimeAPI):

        f = open("monte-learner.out", "w")
        f.write("MONTE Investigator Learner ========================= \n")
        f.close()

        # runtime
        runtime.set_inference_task(self.inference_task)
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.on_input)

        self.in_circle_total = 0
        self.all_total = 0
        while True:
            await self.sim_trigger.wait()

            # launch simulation - use asyncflow dependency resolver
            for x in range(100):
                dt = self.throw_dart()
                self.in_circle_total, self.all_total, pi = await self.train(
                    self.in_circle_total, self.all_total, dt
                )
            f = open("monte-learner.out", "a")
            f.write(f"[{datetime.datetime.now()}] MONTE Publish New Model: {pi} \n")
            f.close()
            runtime.publish_new_model({"pi_val": pi})
            self.sim_trigger.clear()
