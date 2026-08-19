import asyncio
import os
import sys
import time

from radical.asyncflow import WorkflowEngine
from digitaltwin.runtime import RuntimeAPI
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

            for i in range(35):
                await pclient.publish(NUMBER_SENSOR_DTYPE, i)
                await asyncio.sleep(1)

        self.task = task

    async def main_loop(self, runtime: RuntimeAPI, in_data):
        await self.task(runtime.stream_config)


class LetterSensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

        @self.flow.function_task
        async def task(cfg):
            pclient = await cfg.connect()

            alphabet = "abcdefghijklmnopqrstuvwxyz"
            for i in range(26):
                await pclient.publish(LETTER_SENSOR_DTYPE, alphabet[i])
                await asyncio.sleep(1)

        self.task = task

    async def main_loop(self, runtime: RuntimeAPI, in_data):
        await self.task(runtime.stream_config)
