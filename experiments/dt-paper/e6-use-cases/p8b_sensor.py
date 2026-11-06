#!/usr/bin/env python3
"""Fake Davis wind sensor for P8b, with a configurable cadence.

Same records and channel as xGFabric's `service/sensor_publisher.py`
(which publishes every 5 s); `--interval` only shortens the wait until the
investigators have their first 16-reading batch.
"""

import argparse
import asyncio
import datetime
import random

from digitaltwin.streaming import ChannelPublisher

DAVIS_CHANNEL = "xgf/davis"


async def main(interval: float) -> None:
    publisher = await ChannelPublisher.open(DAVIS_CHANNEL)
    n = 0
    try:
        while True:
            r = random.random()
            await publisher.publish({
                "dt": datetime.datetime.now().isoformat(),
                "wind_speed": round(r * 20, 1),
                "wind_avg": round(r * 15, 1),
                "wind_dir": round(r * 360),
            })
            n += 1
            if n % 60 == 0:
                print(f"davis: {n} records", flush=True)
            await asyncio.sleep(interval)
    finally:
        await publisher.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--interval", type=float, default=1.0)
    asyncio.run(main(p.parse_args().interval))
