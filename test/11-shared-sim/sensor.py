import asyncio
import os
import sys

from radical.asyncflow import WorkflowEngine
from digitaltwin.streaming import ZMQ_PS_Client, PubSubClient
from digitaltwin.components import UtilityTask
from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MySensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task
        async def task(cfg):
            pclient = await cfg.connect()

            for i in range(30):
                await asyncio.sleep(1)
                print(f"Sensor val: {i}")
                await pclient.publish(SENSOR_DTYPE, i)

        self.task = task

    async def main_loop(self, runtime, in_data):
        await self.task(runtime.stream_config)
