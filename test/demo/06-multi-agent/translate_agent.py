import asyncio
import datetime


from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import TypedData, SciAgent
from radical.doppelganger.runtime import RuntimeAPI

from translate.translate_investigator import TrInvestigator

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class TranslateAgent(SciAgent):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning. Simple investigator
        self.investigator = TrInvestigator(flow)

        f = open("tr-agent-inference.out", "w")
        f.write("MODEL SELECTOR ========================= \n")
        f.close()

        f = open("tr-agent-learner.out", "w")
        f.write("CROSS MODEL LEARNER ========================= \n")
        f.close()

        @self.flow.function_task
        async def model_select(
            in_data: TypedData, i_id=self.investigator.get_id(), model_kwargs={}
        ):
            f = open("tr-agent-inference.out", "a")
            f.write(
                f"[{datetime.datetime.now()}] Select investigator {i_id}. Use latest model \n"
            )
            f.close()
            return i_id  # default to latest model

        self.model_selector = model_select

    async def main_loop(self, runtime: RuntimeAPI):
        # Start up the investigator
        runtime.start_investigator(self.investigator)

        runtime.set_model_selection_task(self.model_selector)

        # set the investigator for primary inference
        f = open("tr-agent-learner.out", "a")
        f.write(
            f"[{datetime.datetime.now()}] Publish model selector. Param: {self.investigator.get_id()}\n"
        )
        f.close()
        runtime.update_model_selector(i_id=self.investigator.get_id())
