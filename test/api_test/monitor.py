import time

from digitaltwin import NULL_DTYPE, TypedData, UtilityTask
from digitaltwin.components import DataType


class MonitorTask(UtilityTask):
    def __init__(self, out_dtype: DataType, mark_time=False):
        super().__init__(None)
        self.output: list[TypedData] = []
        self.out_dtype = out_dtype
        self.mark_time = mark_time

    async def main_loop(self, runtime, in_data):
        if self.mark_time:
            self.output.append({"data": in_data, "recv_time": time.monotonic()})
        else:
            self.output.append(in_data)
        if self.out_dtype == NULL_DTYPE:
            return
        return TypedData(self.out_dtype, in_data.data)
