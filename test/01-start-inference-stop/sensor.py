"""The sensor, as an external entity: its own process, its own lifetime.

Run it in a terminal of its own, once the broker is up:

    python sensor.py

It publishes JSON on a shared channel and knows nothing about twins.  The
twin binds that channel with `runtime.add_input()`, and a second twin
binding the same channel would receive the same messages.
"""

import asyncio
import time

from digitaltwin.streaming import ChannelPublisher
from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from digitaltwin.runtime import RuntimeAPI
from digitaltwin.streaming import PubSubClient, PubSubConfig
from dtypes import *
import random

import logging

from dtypes import SENSOR_CHANNEL


async def main():
    publisher = await ChannelPublisher.open(SENSOR_CHANNEL)

    try:
        for i in range(30):
            # what the sink measures the end-to-end latency against
            value = time.monotonic_ns()
            print(f"Sensor val: {value} - {i}")

            await publisher.publish(value)
            await asyncio.sleep(0.5)

    finally:
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
