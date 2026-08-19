import asyncio
import datetime
import os
import sys

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from digitaltwin.streaming import PubSubClient
from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class Timer(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data):
        f = open("sensor.out", "w")
        f.write("SENSOR MEASUREMENTS ========================= \n")

        ps = await runtime.stream_config.connect()

        for i in range(30):
            f.write(f"[{datetime.datetime.now()}] Publish: {i} \n")
            await ps.publish(TIMER_TRIGGER_DTYPE, i)
            f.flush()
            await asyncio.sleep(1)

        f.close()
