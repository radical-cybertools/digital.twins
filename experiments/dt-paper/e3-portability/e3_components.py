"""E3 twin components: one agent, N investigators, each placed on a site.

Shipped to the DT service by value (`register_user_modules`).  The agent
gets the site (engine) names as a `Package` kwarg and builds one
investigator per entry; investigator k labels its inference task with
`backend=<site k>`, the explicit-label path of named engines (#62) for
components a component builds itself.  `None` leaves a task on the
session's default engine.

Each inference task holds the GIL for `work_ms` (a busy loop): rhapsody's
concurrent backend runs tasks in a thread pool, so one endpoint process
serves about `1000 / work_ms` requests per second, and a site's capacity,
not the broker's, bounds throughput.  The answer names the endpoint the
task ran on (`DT_TEST_ENDPOINT_TAG`, else the host name), so the result
proves the placement.
"""

import itertools
from typing import Optional

from digitaltwin.components import DataType, ModelInvestigator, SciAgent, TypedData

IN = DataType("e3_request")
OUT = DataType("e3_answer")


class SiteInvestigator(ModelInvestigator):
    """Answers `{site, inv, v}` after `work_ms` of CPU on its site."""

    def __init__(self, flow, inv: int, site: Optional[str], work_ms: float,
                 work: str = "wall"):
        super().__init__(flow)
        label = {} if site is None else {"backend": site}

        @flow.function_task(**label)
        async def work(value, inv=inv, work_ms=work_ms, model=work):
            import os
            import socket
            import time

            # wall: spin until work_ms of wall time has passed (tasks on one
            # endpoint overlap); cpu: until this thread has used work_ms of
            # CPU, so tasks on one endpoint share its GIL (round 5)
            clock = time.thread_time if model == "cpu" else time.perf_counter
            end = clock() + work_ms / 1000.0
            while clock() < end:
                pass
            return {
                "site": os.environ.get("DT_TEST_ENDPOINT_TAG") or socket.gethostname(),
                "inv": inv,
                "v": value,
            }

        self.work = work

    async def main_loop(self, runtime):
        async def infer(in_data: TypedData, **kwargs):
            return TypedData(OUT, await self.work(in_data.data))

        runtime.set_inference_task(infer)
        runtime.publish_new_model({})


class SiteAgent(SciAgent):
    """Round-robins requests over its investigators, one per site entry.

    The selector is a plain coroutine, not a flow task, so selection costs
    no remote task: every request is exactly one task on one site.
    """

    def __init__(self, flow, sites: list, work_ms: float = 50.0, work: str = "wall"):
        super().__init__(flow)
        self.investigators_ = [
            SiteInvestigator(flow, k, site, work_ms, work) for k, site in enumerate(sites)
        ]
        self._next = itertools.count()

    async def model_publish_cb(self, investigator, model_args, acc_metrics):
        pass

    async def main_loop(self, runtime):
        for inv in self.investigators_:
            runtime.start_investigator(inv)
        n = len(self.investigators_)

        async def select(in_data, *args, **kwargs):
            return next(self._next) % n

        runtime.set_model_selection_task(select)
        runtime.update_model_selector()
