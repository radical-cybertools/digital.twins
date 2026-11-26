"""The end of the graph: count predictions, print every 100th."""

from radical.doppelganger import UtilityTask


class Sink(UtilityTask):

    def __init__(self, flow):
        super().__init__(flow)
        self.count = 0

    async def main_loop(self, runtime, in_data):
        self.count += 1
        if self.count % 100 == 0:
            print(f"  sink: {self.count} predictions, last {in_data.data:+.3f}")
