"""The sensor, as an external entity: its own process, its own lifetime.

Run it in a terminal of its own, once the broker is up:

    python sensor.py

It publishes JSON on a shared channel and knows nothing about twins.
"""

import asyncio
from radical.asyncflow import WorkflowEngine
from radical.doppelganger.components import UtilityTask
from radical.doppelganger.runtime import RuntimeAPI
from radical.doppelganger.streaming import PubSubClient, PubSubConfig
from dtypes import *
import random

from radical.doppelganger.streaming import ChannelPublisher

from dtypes import SENSOR_CHANNEL


async def main():
    publisher = await ChannelPublisher.open(SENSOR_CHANNEL)

    try:
        while True:
            await asyncio.sleep(1)

            value = random.random()
            print(f"Sensor val: {value}")

            await publisher.publish(value)

    finally:
        await publisher.close()


if __name__ == "__main__":
    asyncio.run(main())
