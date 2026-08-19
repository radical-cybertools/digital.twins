import asyncio
import os
import sys
import time

from radical.asyncflow import WorkflowEngine
from digitaltwin.streaming import ZMQ_PS_Client, PubSubClient
from digitaltwin.components import UtilityTask
from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class NumberSensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task
        async def task(cfg):
            pclient = await cfg.connect()

            for i in range(5):
                # val = random.random()
                await pclient.publish(NUMBER_SENSOR_DTYPE, i)
                await asyncio.sleep(1)

                await pclient.publish(NUMBER_SENSOR_DTYPE, 100 - i)
                await asyncio.sleep(1)

        self.task = task

    async def main_loop(self, runtime, in_data):
        await self.task(runtime.stream_config)
