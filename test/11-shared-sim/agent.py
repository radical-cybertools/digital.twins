import asyncio


from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData, SciAgent
from digitaltwin.runtime import RuntimeAPI

from positive_model import PositiveModel
from negative_model import NegativeModel

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MyAgent(SciAgent):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning. Simple investigator
        self.plus_inv = PositiveModel(flow)
        self.neg_inv = NegativeModel(flow)

        # shared simulation task
        @self.flow.function_task
        async def shared_sim(number):
            await asyncio.sleep(3)
            return number + 100

        self.shared_selector = shared_sim

        @self.flow.function_task
        async def model_select(in_data: TypedData, i_id, model_kwargs={}):
            return i_id  # default to latest model

        self.model_selector = model_select

    async def main_loop(self, runtime: RuntimeAPI):
        # Start up the investigator
        runtime.start_investigator(self.plus_inv)
        runtime.start_investigator(self.neg_inv)

        runtime.set_model_selection_task(self.model_selector)
        runtime.register_shared_subtask(SHARED_SIM, self.shared_selector)

        # set the investigator for primary inference

        alternate = False
        while True:
            if alternate:
                runtime.update_model_selector(i_id=self.plus_inv.get_id())
            else:
                runtime.update_model_selector(i_id=self.neg_inv.get_id())
            alternate = not (alternate)
            await asyncio.sleep(3)
