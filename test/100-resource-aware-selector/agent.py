import asyncio


import cloudpickle
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, TypedData, SciAgent
from digitaltwin.runtime import RuntimeAPI

from positive_model import PositiveModel
from negative_model import NegativeModel
from profiler.components import TASK_DESCRIPTION_DTYPE, PROFILE_RESULTS

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

        @self.flow.function_task
        async def model_select(in_data: TypedData, models):
            # select the model with the shortest compute time.
            shortest = models[0]
            for model in models:
                if model["pi_runtime"] < shortest["pi_runtime"]:
                    shortest = model

            return shortest["investigator"]  # default to latest model

        self.model_selector = model_select

        self.model_to_process = asyncio.Queue()
        self.models = []

    async def model_publish_cb(
        self, inv: ModelInvestigator, model_args: dict, acc_met: dict
    ):
        await self.model_to_process.put(
            {
                "investigator": inv.get_id(),
                "model_args": model_args,
                "metrics": acc_met,
            }
        )

    async def main_loop(self, runtime: RuntimeAPI):
        # Start up the investigator
        runtime.start_investigator(self.plus_inv)
        runtime.start_investigator(self.neg_inv)

        runtime.set_model_selection_task(self.model_selector)
        # set the investigator for primary inference

        # now, for model selection, do an analysis

        while True:
            item = await self.model_to_process.get()

            infs = runtime.get_inference_tasks()

            raw_inference_task = infs[item["investigator"]].__wrapped__
            task_description = (
                cloudpickle.dumps(raw_inference_task),
                TypedData(SENSOR_DTYPE, 0.20),
                {"offset": 0},
            )
            profile = await runtime.get_inference(
                TypedData(TASK_DESCRIPTION_DTYPE, task_description), PROFILE_RESULTS
            )

            # now, get Pi reading
            pi_runtime = await runtime.get_inference(
                profile, DataType("pi_PREDICT_RUNTIME")
            )

            item["pi_runtime"] = pi_runtime.data
            self.models.append(item)

            print("Current selection: ", self.models)

            if len(self.models) < 10:
                runtime.update_model_selector(models=self.models)
            else:
                # send only last ten.
                runtime.update_model_selector(models=self.models[-10:])
