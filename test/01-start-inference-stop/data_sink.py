import asyncio
import time

from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import UtilityTask
from dtypes import *

import logging

logger = logging.getLogger(__name__)


class MySink(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data):
        final = time.monotonic_ns()
        print(f"Latency: {(final - in_data.data) / 1000000} ms - {final}")
