import asyncio
from concurrent.futures import ProcessPoolExecutor
from rhapsody import Session, ComputeTask
from rhapsody.backends import ConcurrentExecutionBackend


async def main():
    backend = await ConcurrentExecutionBackend(ProcessPoolExecutor())
    session = Session(backends=[backend])

    # 1. Start telemetry — single await, returns TelemetryManager
    telemetry = await session.start_telemetry(
        resource_poll_interval=2.0,  # collect node metrics every 2 s
        checkpoint_path="./telemetry/",  # write a JSONL file here
    )

    # 2. Submit your workload
    tasks = [ComputeTask(executable="/bin/sleep", arguments=["0.1"]) for _ in range(20)]
    async with session:
        await session.submit_tasks(tasks)
        await session.wait_tasks(tasks)
    # session.close() (called by async with) stops telemetry automatically

    # 3. Inspect results — no OTel knowledge required
    print(telemetry.summary())


asyncio.run(main())
