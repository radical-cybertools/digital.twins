import asyncio
import datetime
from radical.asyncflow import WorkflowEngine
from rose import Learner
from radical.doppelganger.components import ModelInvestigator, TypedData
from radical.doppelganger.runtime import RuntimeAPI
from dtypes import *

import logging

logger = logging.getLogger(__name__)


class TrInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # Learners
        self.acl = Learner(self.flow)

        self.to_update = asyncio.Event()

        f = open("tr-model-inference.out", "w")
        f.write("Model Inference Task ========================= \n")
        f.close()

        f = open("tr-model-learner.out", "w")
        f.write("Model Learner ========================= \n")
        f.close()

        self.known_mappings: dict[int, str] = {}

        # Learning tasks..............

        @self.acl.simulation_task(as_executable=False)
        async def simulation(in_num):
            names = [
                "zero",
                "one",
                "two",
                "three",
                "four",
                "five",
                "six",
                "seven",
                "eight",
                "nine",
            ]

            return names[in_num]

        self.simulation = simulation

        # inference task

        @self.flow.function_task
        async def do_inference(in_data: TypedData, labels={}):

            val = labels.get(in_data.data, "Unknown??")

            f = open("tr-model-inference.out", "a")
            f.write(
                f"[{datetime.datetime.now()}] Received input: {in_data.data}. Send: {val}\n"
            )
            f.close()

            return TypedData(ENGLISH_DTYPE, val)

        self.inference_task = do_inference

    # Callbacks .................

    async def text_callback(self, in_data):
        f = open("tr-model-learner.out", "a")
        f.write(f"[{datetime.datetime.now()}] Learner received: {in_data.data} \n")
        f.close()

        if in_data.data not in self.known_mappings:
            self.known_mappings[in_data.data] = "unknown"
            self.to_update.set()

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.text_callback)
        runtime.set_inference_task(self.inference_task)

        # lets train on 0
        self.known_mappings = {}
        while True:
            await self.to_update.wait()
            # I got a new label! train a model
            for i in self.known_mappings:
                if self.known_mappings[i] != "unknown":
                    continue
                self.known_mappings[i] = await self.simulation(i)

            runtime.publish_new_model({"labels": self.known_mappings})
            self.to_update.clear()
