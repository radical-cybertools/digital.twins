import asyncio


from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData, SciAgent
from digitaltwin.runtime import RuntimeAPI

from model import MyModel

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MyAgent(SciAgent):
    def __init__(self, flow: WorkflowEngine, *args, **kwargs):
        super().__init__(flow)
        self.flow = flow

        # no learning. Simple investigator
        self.investigator = MyModel(flow)

        @self.flow.function_task(backend="inference")
        async def model_select(
            in_data: TypedData, i_id=self.investigator.get_id(), model_kwargs={}
        ):
            print("\n RUNNING SELECTOR............ \n")
            return i_id  # default to latest model

        self.model_selector = model_select

    async def main_loop(self, runtime: RuntimeAPI):
        # Start up the investigator
        runtime.start_investigator(self.investigator)

        runtime.set_model_selection_task(self.model_selector)
        # set the investigator for primary inference
        runtime.update_model_selector(i_id=self.investigator.get_id())
