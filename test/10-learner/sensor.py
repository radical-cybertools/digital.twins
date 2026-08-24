import asyncio
import logging
import random

from digitaltwin.components import UtilityTask

from dtypes import SENSOR_DTYPE

logger = logging.getLogger(__name__)


class MySensor(UtilityTask):
    """Persistent source: a stream of raw readings.

    Plain async code on the service loop, publishing through the injected
    stream client -- the persistent-component contract.  Each reading is
    both a learning sample (it feeds the learner through `ON_INPUT`) and
    an inference input.
    """

    def __init__(self, flow, count: int = 200, interval: float = 0.2):
        super().__init__(flow)
        self.count = count
        self.interval = interval

    async def main_loop(self, runtime, in_data):
        for _ in range(self.count):
            await asyncio.sleep(self.interval)
            await runtime.stream.publish(SENSOR_DTYPE, random.uniform(0.0, 10.0))
