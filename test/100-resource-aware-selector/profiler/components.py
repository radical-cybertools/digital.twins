import asyncio
import json


from radical.asyncflow import WorkflowEngine
from digitaltwin.components import DataType, ModelInvestigator, TypedData, SciAgent
from digitaltwin.runtime import RuntimeAPI
from digitaltwin.lru import LRUCache
from rose import Learner

from positive_model import PositiveModel
from negative_model import NegativeModel
import logging
import pandas as pd

from profiler import export_inference_function

logger = logging.getLogger(__name__)

TASK_DESCRIPTION_DTYPE = DataType("task_description_for_profiler")
PROFILE_RESULTS = DataType("profiler_results")


class ProfilerInvestigator(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        @self.flow.executable_task(capture_stdio=True)
        async def exec_profiler(task, example_data: TypedData, model_kwargs: dict):
            if model_kwargs is None:
                model_kwargs = {}

            # fix to use a unique file name.
            export_inference_function("test.pkl", task, example_data, **model_kwargs)

            # call profiler
            return f"python3 profiler.py test.pkl"

        sim_lock = asyncio.Lock()
        sim_lru = LRUCache(128)  # store 128 different sims

        async def do_inference(in_data: TypedData):
            # for inference, just run the simulation.
            async with sim_lock:
                # for now, key only the task code.
                task, example_data, model_kwargs = in_data.data
                if sim_lru.exists(task):
                    return TypedData(PROFILE_RESULTS, sim_lru.fetch_item(task))

                result = await exec_profiler(task, example_data, model_kwargs)
                r = json.loads(result)
                sim_lru.put_item(task, r)
                return TypedData(PROFILE_RESULTS, r)

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)


class ProfilerAgent(SciAgent):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        # no learning. Simple investigator
        self.plus_inv = PositiveModel(flow)
        self.neg_inv = NegativeModel(flow)

        @self.flow.function_task
        async def model_select(in_data: TypedData, i_id, model_kwargs={}):
            return i_id  # default to latest model

        self.model_selector = model_select

    async def main_loop(self, runtime: RuntimeAPI):
        # Start up the investigator
        runtime.start_investigator(self.plus_inv)
        runtime.start_investigator(self.neg_inv)

        runtime.set_model_selection_task(self.model_selector)
        # set the investigator for primary inference

        alternate = False
        while True:
            if alternate:
                runtime.update_model_selector(i_id=self.plus_inv.get_id())
            else:
                runtime.update_model_selector(i_id=self.neg_inv.get_id())
            alternate = not (alternate)
            await asyncio.sleep(3)


class EndpointInvestigator:
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        self.learner = Learner()

        @self.learner.simulation_task(as_executable=False)
        async def sim_database():

            # a CSV with all entries.
            pd.read_csv("data.csv")

            pass

        @self.learner.train
        async def train_model(task, example_data: TypedData, model_kwargs: dict):
            if model_kwargs is None:
                model_kwargs = {}

            # fix to use a unique file name.
            export_inference_function("test.pkl", task, example_data, **model_kwargs)

            # call profiler
            return f"python3 profiler.py test.pkl"

        sim_lock = asyncio.Lock()
        sim_lru = LRUCache(128)  # store 128 different sims

        async def do_inference(in_data: TypedData):
            # for inference, just run the simulation.

            async with sim_lock:
                # for now, key only the task code.
                task, example_data, model_kwargs = in_data.data
                if sim_lru.exists(task):
                    return TypedData(PROFILE_RESULTS, sim_lru.fetch_item(task))

                result = await exec_profiler(task, example_data, model_kwargs)
                r = json.loads(result)
                sim_lru.put_item(task, r)
                return TypedData(PROFILE_RESULTS, r)

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)
