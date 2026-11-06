import asyncio
import time

# adapted from: https://textual.textualize.io/blog/2023/03/08/overhead-of-python-asyncio-tasks/


async def time_tasks(count=100) -> float:
    """Time creating and destroying tasks."""

    async def nop_task() -> None:
        """Do nothing task."""
        pass

    start = time.monotonic()
    tasks = [asyncio.create_task(nop_task()) for _ in range(count)]
    await asyncio.gather(*tasks)
    elapsed = time.monotonic() - start
    return elapsed


for count in range(100_000, 1000_000 + 1, 100_000):
    create_time = asyncio.run(time_tasks(count))
    create_per_second = count / create_time
    print(f"{count:,} tasks \t {create_per_second:0,.0f} tasks per/s")
