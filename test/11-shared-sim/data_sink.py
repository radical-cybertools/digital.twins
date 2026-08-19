import asyncio

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from dtypes import *

import logging

logger = logging.getLogger(__name__)


class MySink(UtilityTask):
    def __init__(self, flow: WorkflowEngine):
        super().__init__(flow)
        self.flow = flow

    async def main_loop(self, runtime, in_data):
        print(f"Received Inference: {in_data.data}")
