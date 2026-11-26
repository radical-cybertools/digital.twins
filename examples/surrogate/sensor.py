"""A synthetic sensor: one reading every `interval` seconds.

A persistent component.  It runs for the lifetime of the twin, takes no
input (it is registered on `TRUTHY`) and publishes into the twin's
stream through `runtime.stream`.  Every reading it publishes is routed
to the components registered for `READING`.

A real sensor is usually a separate process that publishes to a shared
channel; see the "Sensors" section of the concepts page.
"""

import asyncio
import math
import random

from radical.doppelganger import UtilityTask

from dtypes import READING


class Sensor(UtilityTask):

    def __init__(self, flow, interval: float = 0.02):
        super().__init__(flow)
        self.interval = interval

    async def main_loop(self, runtime, in_data):
        while True:
            await asyncio.sleep(self.interval)
            await runtime.stream.publish(READING, random.uniform(0.0, 2 * math.pi))
