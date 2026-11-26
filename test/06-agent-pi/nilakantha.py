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


class Nilakantha(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning.... just inference for now.
        # inference changes given the args passed in.

        @self.flow.function_task
        async def do_inference(in_data: TypedData, pi_val=0):
            return TypedData(PI_DTYPE, pi_val)

        self.inference_task = do_inference

        self.series_n = 1
        self.sum = 3
        self.sim_trigger = asyncio.Event()

        @self.flow.function_task
        async def do_simulation(total, seq_no):
            double = 2 * seq_no
            val = 4 / (double * (double + 1) * (double + 2))
            total += val * (-1) ** (seq_no - 1)
            return total

        self.do_simulation = do_simulation

    async def on_input(self, in_data: TypedData):
        self.sim_trigger.set()

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.on_input)

        self.series_n = 1
        while True:
            await self.sim_trigger.wait()
            # launch simulation
            self.sum = await self.do_simulation(self.sum, self.series_n)
            runtime.publish_new_model({"pi_val": self.sum})
            self.series_n += 1
            self.sim_trigger.clear()
