import asyncio
import time

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import TypedData, UtilityTask
from dtypes import *

import logging

logger = logging.getLogger(__name__)


class MySink(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data: TypedData):
        print(f"Received: {in_data.dtype}:{in_data.data}")
