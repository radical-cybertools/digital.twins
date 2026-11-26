import asyncio
import time

from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import UtilityTask, TypedData

import logging

logger = logging.getLogger(__name__)


class MySink(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data: TypedData):
        final = in_data
        print(f"Got: {in_data.data}  Type: {in_data.dtype}")
