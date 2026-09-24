"""A SciAgent's selection answer, in both spellings the wire produces.

A selector registered as a remote function task returns its
``(investigator_id, model_kwargs)`` pair as a JSON *list* -- the wire
has no tuples.  Both spellings must select.
"""

import pytest

from digitaltwin import (
    DataType,
    DTRuntime,
    ModelInvestigator,
    SciAgent,
    TypedData,
)

NO_FLOW = None

X = DataType("sel-in")
Y = DataType("sel-out")


class Inv(ModelInvestigator):
    async def main_loop(self, runtime):
        async def infer(in_data, k=1.0):
            return TypedData(Y, k * in_data.data)

        runtime.set_inference_task(infer)
        runtime.publish_new_model({"k": 2.0}, {})


class Agent(SciAgent):
    """One investigator; the selector's answer shape is injected."""

    def __init__(self, flow, answer_shape):
        super().__init__(flow)
        self.inv = Inv(flow)
        self.answer_shape = answer_shape

    async def main_loop(self, runtime):
        runtime.start_investigator(self.inv)

        async def select(in_data, i_id=0):
            return self.answer_shape(i_id)

        runtime.set_model_selection_task(select)
        runtime.update_model_selector(i_id=self.inv.get_id())


@pytest.mark.parametrize("shape", [
    lambda i: (i, {"k": 3.0}),   # in-process selector: a tuple
    lambda i: [i, {"k": 3.0}],   # remote function task: JSON made it a list
], ids=["tuple", "list"])
async def test_a_selection_pair_selects_in_both_spellings(
        shape, stream_clients):
    runtime = DTRuntime(NO_FLOW, await stream_clients("agent-sel"))
    runtime.add_agent(Agent(NO_FLOW, shape), X, Y)
    runtime.start()

    answer = await runtime.get_inference(TypedData(X, 7.0), Y)

    assert answer.data == 21.0
    assert runtime.state == "running"

    await runtime.stop()
