"""Round 8b, B2: round 8's WindField-like twin (r8/r8c_components.py) with
the harness corrections from the round 8b page.

Same graph, same task costs, same burst rule (every `every` stream
readings a burst of `every` simulations, one training, a model published
by path) and the same TrendLearner.  Three changes, all in the harness:

  probe marker   a reading with {"probe": True} (the client's low-rate
                 get_inference probe) is ignored by the investigators'
                 ON_INPUT counters and by the TrendLearner, so only the 1 Hz
                 stream drives bursts and trainings.  Round 8's probe fed
                 them too (src/digitaltwin/runtime.py:1543-1547), which
                 halved the burst period to 8 s.
  stream path    the agent's answer carries the reading's publish time
                 (`t_in`); a Sink investigator on the agent's output dtype
                 stamps each answer's arrival (inline ON_INPUT, before
                 anything else runs for it) and keeps the records.  The
                 client fetches them at the end with one get_inference
                 per twin ({"query": True} -> STATS).  The Sink sets
                 `infer_without_consumer = False`, so streamed answers run
                 no inference of its own.
  burst stamps   every published model carries the burst's start time
                 (`t_b0`), so the client sees each investigator's real burst
                 period and can place slow answers against bursts.

The reading publisher and the Sink run on the same node (the client and
the broker are both on node 0), so `t_arrive - t_in` is one clock.
"""

import asyncio
import time

from digitaltwin.components import DataType, ModelInvestigator, SciAgent, TypedData

DAVIS = DataType("r8b_davis")
FIELD = DataType("r8b_field")
TREND = DataType("r8b_trend")
STATS = DataType("r8b_stats")


def _probe(in_data):
    d = in_data.data
    return isinstance(d, dict) and bool(d.get("probe"))


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

        async def inference(in_data, v=0, path=None, t_pub=None, burst_s=None, train_s=None,
                            t_b0=None):
            d = in_data.data if isinstance(in_data.data, dict) else {}
            t_task = await self.infer_task(d)
            return TypedData(FIELD, {"arch": arch, "v": v, "t_pub": t_pub, "burst_s": burst_s,
                                     "train_s": train_s, "t_b0": t_b0, "t_task": t_task,
                                     "t_in": d.get("t_pub"), "probe": bool(d.get("probe"))})

        async def on_input(in_data):
            if _probe(in_data):
                return
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
                                           "train_s": t2 - t1, "t_b0": t0})
            finally:
                self.busy = False

        runtime.set_inference_task(inference)
        runtime.subscribe_to_topic(runtime.ON_INPUT, on_input)
        runtime.publish_new_model({"v": 0, "path": None, "t_pub": time.time()})


class TrendLearner(ModelInvestigator):
    """Windows of `window` stream readings, one `train_s` training task each."""

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
            return TypedData(TREND, {"arch": "trend"})

        async def on_input(in_data):
            if _probe(in_data):
                return
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


class Sink(ModelInvestigator):
    """The agent's consumer: stamps every streamed answer's arrival.

    A query ({"query": True, "since": i}) returns the records from index i
    on; queries are not recorded.
    """

    infer_without_consumer = False

    def __init__(self, flow):
        super().__init__(flow)
        self.records = []

    async def main_loop(self, runtime):
        async def inference(in_data, **kw):
            d = in_data.data if isinstance(in_data.data, dict) else {}
            i = int(d.get("since", 0))
            return TypedData(STATS, {"n": len(self.records), "records": self.records[i:]})

        async def on_input(in_data):
            t = time.time()
            d = in_data.data if isinstance(in_data.data, dict) else {}
            if d.get("query"):
                return
            self.records.append({"t_arrive": t, **{k: d.get(k) for k in
                                 ("t_in", "arch", "v", "t_pub", "burst_s", "train_s", "t_b0",
                                  "t_task")}})

        runtime.set_inference_task(inference)
        runtime.subscribe_to_topic(runtime.ON_INPUT, on_input, inline=True)
        runtime.publish_new_model({})
