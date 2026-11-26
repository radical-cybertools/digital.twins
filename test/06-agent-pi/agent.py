import asyncio
import math


from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import ModelInvestigator, TypedData, SciAgent
from radical.doppelganger.runtime import RuntimeAPI

from gregory import GregoryLeibniz
from nilakantha import Nilakantha
from monte_carlo import MonteCarlo

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MyAgent(SciAgent):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # Three pi investigator
        self.greg = GregoryLeibniz(flow)
        self.nila = Nilakantha(flow)
        self.monte = MonteCarlo(flow)

        @self.flow.function_task
        async def model_select(in_data: TypedData, i_id, name, model_kwargs={}):
            print(f"Model selected: {name}")
            return i_id  # default to latest model

        self.model_selector = model_select

        self.greg_rating = 10000
        self.nila_rating = 10000
        self.monte_rating = 10000
        self.trigger_publish = asyncio.Event()

    async def model_publish_cb(
        self, investigator: ModelInvestigator, model_args: dict, acc_metrics: dict
    ):
        if investigator == self.greg:
            self.greg_rating = abs(math.pi - model_args["pi_val"])
        elif investigator == self.nila:
            self.nila_rating = abs(math.pi - model_args["pi_val"])
        elif investigator == self.monte:
            self.monte_rating = abs(math.pi - model_args["pi_val"])
        self.trigger_publish.set()

    async def main_loop(self, runtime: RuntimeAPI):
        # Start up the investigator
        runtime.start_investigator(self.greg)
        runtime.start_investigator(self.nila)
        runtime.start_investigator(self.monte)

        runtime.set_model_selection_task(self.model_selector)

        # which model is closer to pi?
        while True:
            await self.trigger_publish.wait()

            # which model is lowest
            ratings = {
                "greg": self.greg_rating,
                "nila": self.nila_rating,
                "mote": self.monte_rating,
            }

            ratings = dict(sorted(ratings.items(), key=lambda item: item[1]))

            # get first item
            name, rating = list(ratings.items())[0]
            print(f"Winning: {name}, {rating} of {ratings}")

            if name == "greg":
                runtime.update_model_selector(self.greg.get_id(), "greg")
            elif name == "nila":
                runtime.update_model_selector(self.nila.get_id(), "nila")
            else:
                runtime.update_model_selector(self.monte.get_id(), "monte")

            self.trigger_publish.clear()
