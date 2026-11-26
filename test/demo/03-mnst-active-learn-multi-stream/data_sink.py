import asyncio
import datetime
import time

from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import TypedData, UtilityTask
from dtypes import *

import logging

logger = logging.getLogger(__name__)


class MySink(UtilityTask):
    def __init__(self, flow: WorkflowEngine, fname):
        super().__init__(flow)
        self.flow = flow
        f = open(fname, "w")
        f.write("SINK Receiving ========================= \n")
        f.close()
        self.fname = fname

    async def main_loop(self, runtime, in_data: TypedData):
        f = open(self.fname, "a")
        f.write(f"[{datetime.datetime.now()}] Received: {in_data.data} \n")
        f.close()
