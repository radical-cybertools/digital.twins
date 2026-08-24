import asyncio
import os
import sys

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from digitaltwin.runtime import RuntimeAPI
from digitaltwin.streaming import PubSubClient
from dtypes import *
import random

import logging

logger = logging.getLogger(__name__)


class MySensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, *args, **kwargs):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime: RuntimeAPI, in_data):

        # `runtime.stream` -- not `stream_config.connect()`.  This component
        # runs inline on the service loop, so the twin's own client is right
        # here; opening a second one leaks a context, a socket pair and a
        # receive task per twin, none of which teardown can reach.
        # `stream_config` is for the other case: a task in another process or
        # on another host, which cannot be handed a live client.
        for i in range(10):
            await asyncio.sleep(1)
            val = random.random()
            print(f"Sensor val: {val}")
            await runtime.stream.publish(SENSOR_DTYPE, val)
