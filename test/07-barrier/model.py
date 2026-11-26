import asyncio
import os
import sys
from typing import cast

from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import (
    DataType,
    ModelInvestigator,
    TypedData,
    WindowDataType,
    WindowedTypeData,
)
from radical.doppelganger.runtime import RuntimeAPI

import random

import logging

logger = logging.getLogger(__name__)


class MyModel(ModelInvestigator):
    def __init__(self, flow: WorkflowEngine, is_window=False):
        super().__init__(flow)
        self.flow = flow

        # no learning.... just inference for now.

        # @self.flow.function_task
        async def do_inference(in_data: TypedData):
            if is_window:
                window = cast(WindowedTypeData, in_data)
                w_dtype = cast(WindowDataType, window.dtype)
                t = w_dtype.dtype
                val = window.sequence

            else:
                val = in_data.data
                t = in_data.dtype
            out = DataType(f"INF-{t}")
            return TypedData(out, val)

        self.inference_task = do_inference

    async def main_loop(self, runtime: RuntimeAPI):
        # runtime
        runtime.set_inference_task(self.inference_task)
        runtime.publish_new_model()
