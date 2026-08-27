import asyncio
from concurrent.futures import ProcessPoolExecutor
import time
from rhapsody import Session, ComputeTask
from radical.asyncflow import WorkflowEngine
from rhapsody.backends import ConcurrentExecutionBackend

# Telemetry only


async def main():
    # create engine
    exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
    flow = await WorkflowEngine.create(backend=exe)

    telemetry = await flow.start_telemetry(
        resource_poll_interval=5.0,  # node CPU/memory/GPU every 5 s
        checkpoint_path="./telemetry/",  # write a JSONL file (optional)
    )

    def on_event(event):
        print(event)

    telemetry.subscribe(on_event)

    @flow.function_task
    async def hello():
        return

    a = await hello()

    await flow.shutdown()

    summary = telemetry.summary()
    print(summary)


asyncio.run(main())
