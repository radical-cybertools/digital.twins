import asyncio
import os
import sys
import time

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import DataType, UtilityTask

import random

import logging

from digitaltwin.streaming import PubSubClient

logger = logging.getLogger(__name__)


class MySensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay, output_dt: DataType):
        super().__init__(flow)
        self.flow = flow
        self.delay = delay
        self.output_dt = output_dt

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        for i in range(60):
            print(f"Publish {self.output_dt}. Val: {i}")
            await ps.publish(self.output_dt, i)
            await asyncio.sleep(self.delay)
