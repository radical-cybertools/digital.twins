import logging

from digitaltwin.components import UtilityTask

logger = logging.getLogger(__name__)


class MySink(UtilityTask):
    """Terminal component: prints what the twin predicted."""

    async def main_loop(self, runtime, in_data):
        print(f"prediction: {in_data.data:.3f}")
