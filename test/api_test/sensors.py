"""Persistent utility-task sensors for the api_test digital twin.

Each sensor below is a `UtilityTask` bound with `is_persistent=True` (see
`runtime.add_task(..., TRUTHY, ..., is_persistent=True)` in `run_me.py`).
Its `main_loop` is a single long-running function, structured just like the
external sensor loop in `01-start-inference-stop/sensor.py` (a bounded
`for` loop that computes a value, publishes it, then sleeps) - the only
difference is it publishes in-process via `runtime.stream_config` instead
of through an external `ChannelPublisher`.

Every sensor emits the same payload shape: `(value, timestamp)`, where
`value` is `random.random()` and `timestamp` is `time.monotonic()` at the
moment of publication.
"""

import asyncio
import random
import time

from radical.asyncflow import WorkflowEngine
from digitaltwin.components import UtilityTask
from digitaltwin.streaming import ChannelPublisher

from dtypes import (
    PERSIST_SENSOR_DTYPE,
    FAST_SENSOR_DTYPE,
    SLOW_SENSOR_DTYPE,
    FAST2_SENSOR_DTYPE,
    SLOW2_SENSOR_DTYPE,
    FAST3_SENSOR_DTYPE,
    SLOW3_SENSOR_DTYPE,
    RAND_SENSOR_DTYPE,
    INPUT_CHANNEL,
)

# tests look at output once everything finishes.
N_ITERS = 12


async def input_sensor(config):
    await asyncio.sleep(2)  # to wait for broker to start
    publisher = await ChannelPublisher.open(INPUT_CHANNEL, config=config)
    try:
        for i in range(N_ITERS):
            await asyncio.sleep(1)
            value = {"sensor": i, "sensor_time": time.monotonic()}
            print(f"Input_Sensor val: {i}")
            await publisher.publish(value)

    finally:
        await publisher.close()


class Persist_Sensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay: float = 0.5):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": i, "sensor_time": time.monotonic()}
                print(f"Persist_Sensor val: {i}")
                await ps.publish(PERSIST_SENSOR_DTYPE, value)
                await asyncio.sleep(self.delay)
        finally:
            await ps.close()


class Fast_Sensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay: float = 0.1):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": random.random(), "sensor_time": time.monotonic()}
                # print(f"Fast_Sensor val: {value} - {i}")
                await ps.publish(FAST_SENSOR_DTYPE, value)
                await asyncio.sleep(self.delay)
        finally:
            await ps.close()


class Slow_Sensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay: float = 0.5):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": random.random(), "sensor_time": time.monotonic()}
                # print(f"Slow_Sensor val: {value} - {i}")
                await ps.publish(SLOW_SENSOR_DTYPE, value)
                await asyncio.sleep(self.delay)
        finally:
            await ps.close()


class Fast2_Sensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay: float = 0.2):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": random.random(), "sensor_time": time.monotonic()}
                # print(f"Fast2_Sensor val: {value} - {i}")
                await ps.publish(FAST2_SENSOR_DTYPE, value)
                await asyncio.sleep(self.delay)
        finally:
            await ps.close()


class Slow2_Sensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay: float = 1.0):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": random.random(), "sensor_time": time.monotonic()}
                # print(f"Slow2_Sensor val: {value} - {i}")
                await ps.publish(SLOW2_SENSOR_DTYPE, value)
                await asyncio.sleep(self.delay)
        finally:
            await ps.close()


class Fast3_Sensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay: float = 0.25):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": random.random(), "sensor_time": time.monotonic()}
                # print(f"Fast3_Sensor val: {value} - {i}")
                await ps.publish(FAST3_SENSOR_DTYPE, value)
                await asyncio.sleep(self.delay)
        finally:
            await ps.close()


class Slow3_Sensor(UtilityTask):
    def __init__(self, flow: WorkflowEngine, delay: float = 1.5):
        super().__init__(flow)
        self.delay = delay

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": random.random(), "sensor_time": time.monotonic()}
                # print(f"Slow3_Sensor val: {value} - {i}")
                await ps.publish(SLOW3_SENSOR_DTYPE, value)
                await asyncio.sleep(self.delay)
        finally:
            await ps.close()


class Rand_Sensor(UtilityTask):
    def __init__(
        self, flow: WorkflowEngine, delay_range: tuple[float, float] = (0.1, 1.0)
    ):
        super().__init__(flow)
        self.delay_range = delay_range

    async def main_loop(self, runtime, in_data):
        ps = await runtime.stream_config.connect()
        try:
            for i in range(N_ITERS):
                value = {"sensor": random.random(), "sensor_time": time.monotonic()}
                # print(f"Rand_Sensor val: {value} - {i}")
                await ps.publish(RAND_SENSOR_DTYPE, value)
                await asyncio.sleep(random.uniform(*self.delay_range))
        finally:
            await ps.close()
