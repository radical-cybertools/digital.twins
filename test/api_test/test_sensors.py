from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import sensors


@pytest.mark.parametrize(
    ("sensor_class", "dtype"),
    [
        (sensors.Persist_Sensor, sensors.PERSIST_SENSOR_DTYPE),
        (sensors.Fast_Sensor, sensors.FAST_SENSOR_DTYPE),
        (sensors.Slow_Sensor, sensors.SLOW_SENSOR_DTYPE),
        (sensors.Fast2_Sensor, sensors.FAST2_SENSOR_DTYPE),
        (sensors.Slow2_Sensor, sensors.SLOW2_SENSOR_DTYPE),
        (sensors.Fast3_Sensor, sensors.FAST3_SENSOR_DTYPE),
        (sensors.Slow3_Sensor, sensors.SLOW3_SENSOR_DTYPE),
        (sensors.Fast4_Sensor, sensors.FAST4_SENSOR_DTYPE),
        (sensors.Slow4_Sensor, sensors.SLOW4_SENSOR_DTYPE),
        (sensors.Rand_Sensor, sensors.RAND_SENSOR_DTYPE),
    ],
)
async def test_sensor_uses_runtime_stream(monkeypatch, sensor_class, dtype):
    monkeypatch.setattr(sensors, "N_ITERS", 1)
    monkeypatch.setattr(sensors.asyncio, "sleep", AsyncMock())
    stream = SimpleNamespace(publish=AsyncMock(), close=AsyncMock())
    config = SimpleNamespace(connect=AsyncMock())
    runtime = SimpleNamespace(stream=stream, stream_config=config)

    await sensor_class(None).main_loop(runtime, None)

    stream.publish.assert_awaited_once()
    assert stream.publish.await_args.args[0] == dtype
    assert stream.publish.await_args.args[1]["sensor"] == 0
    config.connect.assert_not_awaited()
    stream.close.assert_not_awaited()
