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


class Timer(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime: RuntimeAPI, in_data):
        counter = 0
        ps = await runtime.stream_config.connect()
        while True:
            await ps.publish(TIMER_TRIGGER_DTYPE, counter)
            await asyncio.sleep(1)
