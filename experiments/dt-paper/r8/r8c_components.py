"""Round 8, R8-C: a WindField-like twin with synthetic tasks at measured costs.

The graph of xGFabric's WindField twin (e6-use-cases/p8b_client.py), with
every task a CPU-bound stand-in of the cost round 8 measured:

  input      one Davis-like stream per twin (the harness publishes 1 Hz)
  agent      WindAgent: a selector task (~1 ms) on the inference engine,
             then the chosen investigator's inference: 80% PINN (20 ms
             CPU), 20% FNO (120 ms CPU), as the selector chose in B3
  3 surrogate investigators (pinn, fno, pcr): every `every` readings a
             burst of `every` simulations (0.25 s CPU each) and one training
             task (2 s CPU) on the twin's learning engine, then a model
             published by path (a file of R8-E's measured FNO size; the
             inference task does not read it: a warm model)
  learner    TrendLearner: windows of 4 readings, one 4 s training task
             each, on the learning engine (xGFabric's WindTrendLearner shape)

Simulations and trainings are compressed (real CFD is about 400 s on 32
cores): the framework's load is the task count and rate, not the duration.
Every inference answer carries the model version, its publish time and the
last burst's makespan and training time, so the client can measure the
model-update delay and the burst makespan from the answers alone.
"""

import asyncio
import time

from digitaltwin.components import DataType, ModelInvestigator, SciAgent, TypedData

DAVIS = DataType("r8c_davis")
FIELD = DataType("r8c_field")


def _spin(seconds):
    end = time.thread_time() + seconds
    while time.thread_time() < end:
        pass


class SurrogateInv(ModelInvestigator):

    def __init__(self, flow, arch: str, infer_ms: float, learn: str | None,
                 model_path: str, every: int = 16, sim_s: float = 0.25, train_s: float = 2.0):
        super().__init__(flow)
        self.arch, self.every, self.model_path = arch, every, model_path
        self.readings = 0
        self.busy = False
        label = {} if learn is None else {"backend": learn}

        async def infer(x, cost=infer_ms / 1000.0):
            import time as _t
            end = _t.thread_time() + cost
            while _t.thread_time() < end:
                pass
            return _t.time()

        async def simulate(point, cost=sim_s):
            import time as _t
            end = _t.thread_time() + cost
            while _t.thread_time() < end:
                pass
            return point

        async def train(n, cost=train_s):
            import time as _t
            end = _t.thread_time() + cost
            while _t.thread_time() < end:
                pass
            return n

        self.infer_task = flow.function_task(infer)
        self.sim_task = flow.function_task(simulate, **label)
        self.train_task = flow.function_task(train, **label)

    async def main_loop(self, runtime):
        arch = self.arch

        async def inference(in_data, v=0, path=None, t_pub=None, burst_s=None, train_s=None):
            t_task = await self.infer_task(in_data.data)
            return TypedData(FIELD, {"arch": arch, "v": v, "t_pub": t_pub, "burst_s": burst_s,
                                     "train_s": train_s, "t_task": t_task})

        async def on_input(in_data):
            self.readings += 1
            if self.readings % self.every or self.busy:
                return
            self.busy = True
            try:
                t0 = time.time()
                await asyncio.gather(*[self.sim_task(i) for i in range(self.every)])
                t1 = time.time()
                await self.train_task(self.readings)
                t2 = time.time()
                runtime.publish_new_model({"v": self.readings // self.every, "path": self.model_path,
                                           "t_pub": time.time(), "burst_s": t1 - t0,
                                           "train_s": t2 - t1})
            finally:
                self.busy = False

        runtime.set_inference_task(inference)
        runtime.subscribe_to_topic(runtime.ON_INPUT, on_input)
        runtime.publish_new_model({"v": 0, "path": None, "t_pub": time.time()})


class TrendLearner(ModelInvestigator):
    """Windows of `window` readings, one `train_s` training task each."""

    def __init__(self, flow, learn: str | None, window: int = 4, train_s: float = 4.0):
        super().__init__(flow)
        self.window, self.n, self.busy = window, 0, False
        label = {} if learn is None else {"backend": learn}

        async def train(n, cost=train_s):
            import time as _t
            end = _t.thread_time() + cost
            while _t.thread_time() < end:
                pass
            return n

        self.train_task = flow.function_task(train, **label)

    async def main_loop(self, runtime):
        async def inference(in_data, **kw):
            return TypedData(FIELD, {"arch": "trend"})

        async def on_input(in_data):
            self.n += 1
            if self.n % self.window or self.busy:
                return
            self.busy = True
            try:
                await self.train_task(self.n)
            finally:
                self.busy = False

        runtime.set_inference_task(inference)
        runtime.subscribe_to_topic(runtime.ON_INPUT, on_input)
        runtime.publish_new_model({})


class WindAgent(SciAgent):
    """Selector (~1 ms task) in front of pinn / fno / pcr; 80% pinn, 20% fno."""

    def __init__(self, flow, learn: str | None, model_path: str, every: int = 16):
        super().__init__(flow)
        self.invs = [SurrogateInv(flow, "pinn", 20.0, learn, model_path, every),
                     SurrogateInv(flow, "fno", 120.0, learn, model_path, every),
                     SurrogateInv(flow, "pcr", 20.0, learn, model_path, every)]

        async def select(in_data, *args, **kwargs):
            import random as _r
            import time as _t
            end = _t.thread_time() + 0.001
            while _t.thread_time() < end:
                pass
            return 0 if _r.random() < 0.8 else 1

        self.select_task = flow.function_task(select)

    async def model_publish_cb(self, investigator, model_args, acc_metrics):
        pass

    async def main_loop(self, runtime):
        for inv in self.invs:
            runtime.start_investigator(inv)
        runtime.set_model_selection_task(self.select_task)
        runtime.update_model_selector()
