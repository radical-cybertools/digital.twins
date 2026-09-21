"""Model investigator for the api_test digital twin.

`StampModel`'s inference task simply stamps every input with the current
model version and a timestamp. The version is bumped every `UPDATE_EVERY`
inputs via the `on_input` callback, which then republishes the model --
mirroring `03-conditional-redeploy/model.py`'s conditional-redeploy pattern,
except the trigger is an input count instead of a value threshold.
"""

import asyncio
import random
import string
import time

from digitaltwin import SplitTask
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import ModelInvestigator, SciAgent, TypedData
from digitaltwin.runtime import RuntimeAPI

from dtypes import (
    FLIP_AGENT_IN,
    FLIP_AGENT_OUT,
    INVESTIGATOR_OUT_DTYPE,
    AGENT_OUT_DTYPE,
    NEG_NUM,
    POS_NUM,
)

UPDATE_EVERY = 2


class InvestigatorTest(ModelInvestigator):
    def __init__(self):
        super().__init__(None)
        self.version = 1
        self.count = 0
        self.to_publish = asyncio.Event()

        async def do_inference(in_data: TypedData, version=1):
            return TypedData(
                INVESTIGATOR_OUT_DTYPE,
                {
                    "version": version,
                    "timestamp": time.monotonic(),
                    "dat": in_data.data,
                },
            )

        self.inference_task = do_inference

    async def on_input(self, in_data: TypedData):
        self.count += 1
        if self.count % UPDATE_EVERY == 0:
            self.version += 1
            self.to_publish.set()

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model({"version": self.version})
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.on_input)

        while True:
            await self.to_publish.wait()
            runtime.publish_new_model({"version": self.version})
            self.to_publish.clear()


class LetterInvestigator(ModelInvestigator):
    """One of `TestAgent`'s two investigators: stamps version + timestamp,
    same as `TestInvestigator`, plus a random 6-letter sequence -- so a
    model-selection test can tell which investigator answered."""

    def __init__(self, upper: bool = False):
        super().__init__(None)
        self.version = 0
        self.alphabet = string.ascii_uppercase if upper else string.ascii_lowercase

        async def do_inference(
            in_data: TypedData,
            version=0,
            fcount=0,
            fcount_out=0,
            out_count=0,
            flip=None,
        ):
            if flip is None:
                flip = {}

            letters = "".join(random.choices(self.alphabet, k=6))
            return TypedData(
                AGENT_OUT_DTYPE,
                {
                    "version": version,
                    "timestamp": time.monotonic(),
                    "letters": letters,
                    "dat": in_data.data,
                    "fcount": fcount,
                    "fcount_out": fcount_out,
                    "out_count": out_count,
                    "flip": flip,
                },
            )

        self.inference_task = do_inference
        self.to_publish = asyncio.Event()
        self.count = 0
        self.filter_count = 0
        self.filter_out_count = 0
        self.out_count = 0
        self.upper = upper

    async def on_input(self, in_data: TypedData):
        self.version += 1

    async def on_filtered_input(self, in_data: TypedData):
        self.filter_count += 1
        self.count += 1
        if self.count % UPDATE_EVERY == 0:
            self.to_publish.set()

    async def on_filtered_output(self, in_data: TypedData):
        self.filter_out_count += 1

    async def on_output(self, in_data: TypedData):
        self.out_count += 1

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model({"version": self.version})
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.on_input)
        runtime.subscribe_to_topic(runtime.ON_FILTERED_INPUT, self.on_filtered_input)
        runtime.subscribe_to_topic(runtime.ON_FILTERED_OUTPUT, self.on_filtered_output)
        runtime.subscribe_to_topic(runtime.ON_OUTPUT, self.on_output)
        while True:
            await self.to_publish.wait()
            m_arg = {
                "version": self.version,
                "fcount": self.filter_count,
                "fcount_out": self.filter_out_count,
                "out_count": self.out_count,
            }
            runtime.publish_new_model(m_arg)
            self.to_publish.clear()


class AgentTest(SciAgent):
    """A SciAgent with two `LetterInvestigator`s and a pass-through model
    selector, mirroring `05-agent-w-multi-investigators/agent.py`."""

    def __init__(self):
        super().__init__(None)
        self.inv_lower = LetterInvestigator(upper=False)
        self.inv_upper = LetterInvestigator(upper=True)

        self.model_low = {}
        self.model_up = {}

        self.update = asyncio.Event()

        async def model_select(in_data: TypedData, i_id, model_kwargs={}):
            return i_id, model_kwargs  # default to latest model

        self.model_selector = model_select

    async def model_publish_cb(
        self, investigator: ModelInvestigator, model_args: dict, acc_metrics: dict
    ):
        if investigator == self.inv_upper:
            self.model_up = model_args
        else:
            self.model_low = model_args
        self.update.set()

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.start_investigator(self.inv_lower)
        runtime.start_investigator(self.inv_upper)
        runtime.set_model_selection_task(self.model_selector)

        # is overwritten by the model publish cb... UP is called last (default model)
        runtime.update_model_selector(i_id=self.inv_upper.get_id())

        toggle = False
        while True:
            await self.update.wait()
            toggle = not (toggle)
            marg = {}
            if toggle:
                inv = self.inv_upper.get_id()
                marg = self.model_up
                code = "upper"
            else:
                inv = self.inv_lower.get_id()
                marg = self.model_low
                code = "LOWER"

            # will call switchcase on code
            val = await runtime.get_inference(
                TypedData(FLIP_AGENT_IN, code), FLIP_AGENT_OUT
            )
            assert val is not None
            marg["flip"] = val.data

            runtime.update_model_selector(i_id=inv, model_kwargs=marg)
            self.update.clear()


class FlipInvestigator(ModelInvestigator):
    def __init__(self):
        super().__init__(None)
        self.version = 0

        async def do_inference(
            in_data: TypedData,
            version=0,
            fcount=0,
            fcount_out=0,
            out_count=0,
        ):
            return TypedData(
                FLIP_AGENT_OUT,
                {
                    "version": version,
                    "timestamp": time.monotonic(),
                    "swap": in_data.data.swapcase(),
                    "fcount": fcount,
                    "fcount_out": fcount_out,
                    "out_count": out_count,
                },
            )

        self.inference_task = do_inference
        self.to_publish = asyncio.Event()
        self.count = 0
        self.filter_count = 0
        self.filter_out_count = 0
        self.out_count = 0

    async def on_input(self, in_data: TypedData):
        self.version += 1

    async def on_filtered_input(self, in_data: TypedData):
        self.filter_count += 1
        self.count += 1
        if self.count % UPDATE_EVERY == 0:
            self.to_publish.set()

    async def on_filtered_output(self, in_data: TypedData):
        self.filter_out_count += 1

    async def on_output(self, in_data: TypedData):
        self.out_count += 1

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model({"version": self.version})
        runtime.subscribe_to_topic(runtime.ON_INPUT, self.on_input)
        runtime.subscribe_to_topic(runtime.ON_FILTERED_INPUT, self.on_filtered_input)
        runtime.subscribe_to_topic(runtime.ON_FILTERED_OUTPUT, self.on_filtered_output)
        runtime.subscribe_to_topic(runtime.ON_OUTPUT, self.on_output)

        while True:
            await self.to_publish.wait()
            m_arg = {
                "version": self.version,
                "fcount": self.filter_count,
                "fcount_out": self.filter_out_count,
                "out_count": self.out_count,
            }
            runtime.publish_new_model(m_arg)
            self.to_publish.clear()


class FlipAgent(SciAgent):
    def __init__(self):
        super().__init__(None)
        self.flip = FlipInvestigator()

        self.update = asyncio.Event()

        async def model_select(in_data: TypedData, i_id, model_kwargs={}):
            return i_id  # default to latest model

        self.model_selector = model_select

    async def main_loop(self, runtime: RuntimeAPI):
        runtime.start_investigator(self.flip)

        runtime.set_model_selection_task(self.model_selector)
        runtime.update_model_selector(i_id=self.flip.get_id())


class SplitTest(SplitTask):
    def __init__(self):
        super().__init__(None)

    async def main_loop(self, runtime: RuntimeAPI, in_data: TypedData):
        # runtime
        if in_data.data["sensor"] >= 0:
            return TypedData(POS_NUM, in_data.data), None

        return None, TypedData(NEG_NUM, in_data.data)
