from concurrent.futures import ProcessPoolExecutor
from radical.asyncflow import WorkflowEngine, NoopExecutionBackend
from rhapsody.backends import ConcurrentExecutionBackend
import time
import asyncio

if __name__ == "__main__":

    async def main():
        exe = await ConcurrentExecutionBackend(ProcessPoolExecutor())
        # exe = NoopExecutionBackend()
        flow = await WorkflowEngine.create(backend=exe)

        @flow.function_task
        async def nop_task():
            return

        @flow.block
        async def block_task():
            return

        async def plain():
            return

        def seq_plain():
            return

        async def pipeline(count):
            start = time.monotonic()
            tasks = [nop_task() for _ in range(count)]
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start
            return elapsed

        async def pipeline_block(count):
            start = time.monotonic()
            tasks = [block_task() for _ in range(count)]
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start
            return elapsed

        async def pipeline_plain(count):
            start = time.monotonic()
            tasks = [plain() for _ in range(count)]
            await asyncio.gather(*tasks)
            elapsed = time.monotonic() - start
            return elapsed

        def sequential(count):
            start = time.monotonic()
            tasks = [seq_plain() for _ in range(count)]
            elapsed = time.monotonic() - start
            return elapsed

        print("Function Tasks: ")
        for count in range(1_000, 10_000 + 1, 1_000):
            create_time = await pipeline(count)
            create_per_second = count / create_time
            print(f"{count:,} function tasks \t {create_per_second:0,.0f} tasks per/s")

        print("Blocks: ")
        for count in range(1_000, 10_000 + 1, 1_000):
            create_time = await pipeline_block(count)
            create_per_second = count / create_time
            print(f"{count:,} blocks \t {create_per_second:0,.0f} blocks per/s")

        print("Plain Async: ")
        for count in range(1_000, 10_000 + 1, 1_000):
            create_time = await pipeline_plain(count)
            create_per_second = count / create_time
            print(
                f"{count:,} plain async tasks \t {create_per_second:0,.0f} plain async tasks per/s"
            )

        print("Sequential: ")
        for count in range(1_000, 10_000 + 1, 1_000):
            create_time = sequential(count)
            create_per_second = count / create_time
            print(f"{count:,} strait def \t {create_per_second:0,.0f} func per/s")

        await flow.shutdown()

    asyncio.run(main())
