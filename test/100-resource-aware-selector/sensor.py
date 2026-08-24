import asyncio
import os
import sys

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from digitaltwin.runtime import RuntimeAPI
from digitaltwin.streaming import PubSubClient, PubSubConfig
from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MySensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task
        async def test(ps_config: PubSubConfig):
            ps = await ps_config.connect()
            for i in range(30):
                val = random.random()
                print(f"Sensor val: {val} - {i}")
                await ps.publish(SENSOR_DTYPE, val)
                await asyncio.sleep(1)

        self.task = test

    async def main_loop(self, runtime: RuntimeAPI, in_data):
        await self.task(runtime.stream_config)
