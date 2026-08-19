import asyncio
import os
import sys

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import SplitTask, TypedData
from digitaltwin.runtime import RuntimeAPI

from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class HighLow(SplitTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)

    async def main_loop(self, runtime: RuntimeAPI, in_data: TypedData):
        # runtime
        if in_data.data > 50:
            return TypedData(HIGH_NUMBER_DTYPE, in_data.data), None

        return None, TypedData(LOW_NUMBER_DTYPE, in_data.data)
