# src/digitaltwin/components.py
"""Core data structures and component base classes for the digital-twin system.

This module defines lightweight dataclasses, helper utility classes, and
abstract component types that are used throughout the runtime.
"""

from abc import ABC, abstractmethod
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from radical.asyncflow import WorkflowEngine

# ------------------------------------------------------------------


@dataclass
class DataType:
    """Represent a lightweight identifier for the shape of data that flows
    through the digital-twin system.  Only the ``name`` field is stored,
    and equality/hash are based on that ``name``.

    Args:
        name: Human-readable name of the datatype. Defaults to ``"None"``.

    """

    name: str = "None"

    # write fields of the data type here
    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, obj) -> bool:
        if isinstance(obj, (WindowDataType, JoinDataType)):
            # this should always be false, as SELF is polymorphed
            # and will use the subclass __eq__, not this one.
            return False

        return isinstance(obj, DataType) and obj.name == self.name

    def __str__(self) -> str:
        return self.name


TRUTHY = DataType("TRUE")
NULL_DTYPE = DataType("NULL")

# ------------------------------------------------------------------


@dataclass
class TypedData:
    """Associate a concrete payload with a ``DataType``.
    The payload can be any Python object.

    Args:
        dtype: The ``DataType`` that describes the structure of ``data``.
        data:  The actual value of the payload.

    Returns:
        None - this is a plain data container.
    """

    dtype: DataType
    data: Any


# ------------------------------------------------------------------


@dataclass
class JoinDataType(DataType):
    """Describe a composite data type produced by joining multiple independent
    input types.  It is represented as ``JOIN[a,b,c]`` where ``a,b,c`` are
    the names of the individual sub-data-types.

    Args:
        dtypes: List of participating ``DataType`` objects.

    """

    dtypes: list[DataType] = field(default_factory=list)

    def __init__(self, dtypes: list[DataType]) -> None:
        super().__init__(name=f"JOIN[{','.join(str(d) for d in dtypes)}]")
        self.dtypes = dtypes

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, obj) -> bool:
        if (
            not isinstance(obj, JoinDataType)
            or self.name != obj.name
            or len(obj.dtypes) != len(self.dtypes)
        ):
            return False

        # check sub dtypes
        for i in range(len(self.dtypes)):
            if self.dtypes[i] != obj.dtypes[i]:
                return False

        return True

    def __str__(self) -> str:
        return super().__str__()


# ------------------------------------------------------------------


@dataclass
class JoinedTypedData(TypedData):
    """Concrete data carrying the result of a join operation.  Its ``data``
    field is a *list* of the ``TypedData`` instances that produced the
    joined value.

    Args:
        dtype:   The ``JoinDataType`` instance describing the join.
        data:    List of ``TypedData`` objects, one per input type.
    """

    data: list[TypedData]


# ------------------------------------------------------------------


@dataclass
class WindowDataType(DataType):
    """Mark a datatype that will be produced at the barrier.  It contains a
    single underlying datatype and a generated name of the form
    ``W[<dtype> by B-<barrier_name>]``.

    Args:
        dtype: The underlying datatype this window refers to.
        name:  Name of the barrier that will emit this type.
    """

    dtype: DataType = NULL_DTYPE

    def __init__(self, dtype: DataType, name: str) -> None:
        super().__init__(name=f"W[{dtype} by B-{name}]")
        self.dtype = dtype

    def __hash__(self) -> int:
        return super().__hash__()

    def __eq__(self, obj) -> bool:
        return (
            isinstance(obj, WindowDataType)
            and obj.dtype == self.dtype
            and obj.name == self.name
        )

    def __str__(self) -> str:
        return super().__str__()


# ------------------------------------------------------------------


@dataclass
class WindowedTypeData(TypedData):
    """Represent a FIFO window of values from a single datatype.  The
    window is read-only for callers and is produced by a soft barrier.

    Args:
        dtype: This ``WindowDataType``.
        sequence: Ordered list of the most recent values (oldest first).
    """

    sequence: list[Any]

    def __init__(self, dtype: WindowDataType, sequence: list[Any]) -> None:
        super().__init__(dtype=dtype, data=sequence)
        self.sequence = sequence


# ------------------------------------------------------------------


@dataclass(frozen=True, eq=True)
class SharedSubtaskLabel:
    """Lightweight key to register a reusable sub-task on a ``SciAgent``.
    The label is just a string that is used as a dictionary key.

    Args:
        label: Identifier for the sub-task.
    """

    label: str

    def __str__(self) -> str:
        return self.label


# ------------------------------------------------------------------


class _TwinComponent:
    """Abstract base class for all component types.  Provides a minimal
    interface that the runtime uses to call a component's main loop.
    Implementations must provide ``main_loop``.
    """

    def __init__(self) -> None:
        pass

    async def main_loop(self, runtime, *args, **kwargs) -> TypedData | None:
        """Entry point for a component's run loop.

        Args:
            runtime: Reference to the runtime instance.
            *args, **kwargs: Arbitrary arguments passed by the runtime.

        Returns:
            Optional :class:`TypedData` - the component's output or
            ``None`` if it discards the data.
        """
        raise NotImplementedError


# ------------------------------------------------------------------


class ModelInvestigator(_TwinComponent):
    """Model-oriented investigation step.  ``flow`` is a
    ``WorkflowEngine`` that drives investigator callbacks.
    """

    def __init__(self, flow: WorkflowEngine) -> None:
        super().__init__()
        self.flow = flow
        # for use by SciAgent
        self.runtime_id: Optional[int] = None

    def agent_feedback(self, *args, **kwargs) -> None:
        """Hook for sending runtime-level feedback to the investigator.
        Implementations can record state or adjust internal models.
        """
        pass

    def get_id(self):
        """Return the runtime ID assigned by the runtime."""
        return self.runtime_id

    # callbacks
    # async def my_callback(self, in_data: TypedData):
    #     pass

    # # inference task signature:
    # async def inference_task(in_data: TypedData, **model_kwargs) --> TypedData:
    #    pass

    # inference tasks also receive typed data and must return typed data

    def __eq__(self, obj):
        if isinstance(obj, ModelInvestigator):
            return self.runtime_id == obj.runtime_id
        else:
            return False

    async def main_loop(self, runtime, *args, **kwargs) -> TypedData | None:
        # Placeholder - subclasses provide the actual logic.
        return None


class UtilityTask(_TwinComponent):
    """Single-use or persistent helper that transforms data in-situ.
    ``flow`` schedules internal callbacks.
    """

    def __init__(self, flow: WorkflowEngine) -> None:
        super().__init__()
        self.flow = flow

    async def main_loop(
        self, runtime, in_data: TypedData, *args, **kwargs
    ) -> TypedData | None:
        # Implement actual transformation logic here.
        return None


# ------------------------------------------------------------------


class SplitTask(UtilityTask):
    """A task that receives an incoming TypedData stream and can split it into
    multiple TypedData streams. Runs in-situ"""

    def __init__(self, flow: WorkflowEngine) -> None:
        super().__init__(flow)

    # runs one instance per event, similar to non-persistent utility task
    # expects a tuple of TypedData, with the same dtypes matching
    # what the runtime was given at graph creation
    async def main_loop(self, runtime, in_data: TypedData):
        # return TypedData(DataType("a"), 1), TypedData(DataType("b"), 2)
        raise NotImplementedError


# ------------------------------------------------------------------


class SciAgent(_TwinComponent):
    """Science agent owning multiple investigators. Captures one physics
    property. (One in-out pair of DataTypes)
    ``flow`` schedules agent
    logic.
    """

    def __init__(self, flow: WorkflowEngine) -> None:
        super().__init__()
        self.flow = flow
        self.investigators: dict[int, ModelInvestigator] = {}
        self._investigator_counter = -1

    def _generate_runtime_id(self):
        self._investigator_counter += 1
        return self._investigator_counter

    # # model selector signature:
    # async def model_select_task(in_data: TypedData, *model_select_args, **model_select_kwargs):
    #    return investigator_id, model_args
    #
    #    Model args returned are passed to the investigator inference task's
    #    model_args
    #
    #    IF returned model_args is NONE or missing, use latest model published by investigator

    async def model_publish_cb(
        self, investigator: ModelInvestigator, model_args: dict, acc_metrics: dict
    ) -> None:
        """Callback fired when a model investigator publishes a new model.

        Args:
            investigator: The publishing investigator.
            model_args:    Hyper-parameters for the model.
            acc_metrics:   Accuracy metrics.
        """
        pass

    async def main_loop(self, runtime) -> None:
        # Implement agent’s run logic here.
        pass


# ------------------------------------------------------------------


class Barrier:
    """Synchronizes several data streams.  Handles hard and soft
    synchronization.

    Hard: block all output until item is received.
    Soft: will output latest seen value when other streams resolve.

    (If all are soft, then output on every incoming event)
    """

    def __init__(self, name: str, hard: bool = True) -> None:
        self.is_hard_barrier = hard
        self.name = name
        self.output_queues: dict[DataType, asyncio.Queue] = {}
        self.global_version = 0
        self.dtypes: dict[DataType, bool] = {}
        self.previous: dict[DataType, list[Any]] = defaultdict(list)
        self.previous_retain: dict[DataType, bool] = {}

        # default: -1
        self.version_numbers: dict[DataType, int] = {}
        self.condition = asyncio.Condition()
        self._update = asyncio.Semaphore(0)
        self.count_hard = 0
        self.count_soft = 0
        self.set_soft = False
        self.recv_soft = 0

    def __str__(self) -> str:
        return self.name

    def add_dtype(self, dtype: DataType, hard: Optional[bool] = None):
        """Add a typed stream for the barrier to synchronize.

        Args:
            dtype (DataType): DataType of stream
            hard (Optional[bool], optional): Hard barrier or soft. Hard blocks
            until receives data. Soft is optimistic and emits data when barrier
            resolves. Defaults to hardness set in constructor.

        Returns:
            dtype: DataType output. A windowed datatype if a soft barrier.
        """
        if hard is None:
            hard = self.is_hard_barrier

        if dtype in self.dtypes:
            # already exists!
            raise ValueError(f"Dtype {dtype} already added!")

        self.dtypes[dtype] = hard
        self.version_numbers[dtype] = self.global_version - 1
        self.output_queues[dtype] = asyncio.Queue()
        self.count_hard += int(hard)
        self.count_soft += int(not hard)
        return dtype if hard else WindowDataType(dtype, self.name)

    async def put(self, in_data: TypedData):
        dtype = in_data.dtype
        if not (self.dtypes[dtype]):
            # soft. just store the result
            if len(self.previous[dtype]) == 0:
                self.recv_soft += 1

            if self.previous_retain.get(dtype, True):
                self.previous[dtype] = [in_data.data]
                self.previous_retain[dtype] = False
            else:
                self.previous[dtype].append(in_data.data)

            if self.count_hard == 0 and not self.set_soft:
                self.set_soft = True
                self._update.release()
            return

        def predicate():
            return self.version_numbers[dtype] < self.global_version

        # not ok to increment. WAIT for self.version_numbers[dtype] < self.global_version
        async with self.condition:
            while True:
                await self.condition.wait_for(predicate)
                if self.version_numbers[dtype] < self.global_version:
                    # OK to increment
                    self.version_numbers[dtype] += 1

                    if dtype not in self.output_queues:
                        self.output_queues[dtype] = asyncio.Queue()

                    # is hard
                    # V() on update
                    self._update.release()
                    self.output_queues[dtype].put_nowait(in_data)
                    return

    async def get(self, dtype: DataType, wait: bool = True) -> TypedData:
        """Get item from the barrier.

        Args:
            dtype (DataType): Stream dtype
            wait (bool, optional): Wait for barrier or not. Defaults to True.

        Raises:
            ValueError: If data type requested is unknown (assumes non-windowed version)

        Returns:
            TypedData
        """
        if dtype not in self.output_queues:
            raise ValueError("Unrecognized datatype for barrier")
        if wait:
            return await self.output_queues[dtype].get()
        else:
            return self.output_queues[dtype].get_nowait()

    async def run(self):
        """Barrier main loop.  Runs until cancelled -- the runtime owns the
        task (see `DTRuntime.add_barrier`), so it is cancelled on stop and
        its failures are routed into the runtime state."""

        # wait for there to be at least one task
        while self.count_soft + self.count_hard == 0:
            await asyncio.sleep(0.01)
        while True:
            await self.condition.acquire()
            self.condition.notify_all()
            self.condition.release()

            # The update will only fire until ALL the soft items gets something.
            if self.recv_soft < self.count_soft:
                await asyncio.sleep(0.01)
                continue

            # did all hard vals update.
            for i in range(self.count_hard):
                await self._update.acquire()

            if self.count_hard == 0:
                await self._update.acquire()

            self.set_soft = False
            for dtype in self.dtypes:
                if self.dtypes[dtype]:
                    continue
                # emit on any soft barriers
                # drain previous in reverse append order
                self.output_queues[dtype].put_nowait(
                    WindowedTypeData(
                        WindowDataType(dtype, self.name), self.previous[dtype]
                    )
                )
                self.previous[dtype] = [self.previous[dtype][-1]]
                self.previous_retain[dtype] = True

            # all updates have been sent. Increment global version
            self.global_version += 1


if __name__ == "__main__":
    # Barrier test

    apple = DataType("apple")
    orange = DataType("orange")
    pear = DataType("pear")

    b = Barrier("barrier1")

    async def apple_producer() -> None:
        counter = 0
        while True:
            print(f"Produce apple: {counter}")
            await b.put(TypedData(apple, counter))
            counter += 1
            await asyncio.sleep(1)

    async def orange_producer() -> None:
        counter = 0
        while True:
            print(f"Produce orange: {counter}")
            await b.put(TypedData(orange, counter))
            counter += 1
            await asyncio.sleep(2)

    async def pear_producer() -> None:
        counter = 0
        while True:
            print(f"Produce pear: {counter}")
            await b.put(TypedData(pear, counter))
            counter += 1
            await asyncio.sleep(5)

    async def apple_consumer() -> None:
        while True:
            out = await b.get(apple)
            print(f"Consume apple: {out.data}")

    async def orange_consumer() -> None:
        while True:
            out = await b.get(orange)
            print(f"Consume orange: {out.data}")

    async def pear_consumer() -> None:
        while True:
            out = await b.get(pear)
            print(f"Consume pear: {out.data}")

    async def main() -> None:

        b.add_dtype(apple)
        b.add_dtype(orange)
        b.add_dtype(pear, hard=True)

        asyncio.create_task(b.run())

        t1 = asyncio.create_task(apple_producer())
        t2 = asyncio.create_task(orange_producer())
        t3 = asyncio.create_task(pear_producer())

        # consumer

        t1 = asyncio.create_task(apple_consumer())
        t2 = asyncio.create_task(orange_consumer())
        t3 = asyncio.create_task(pear_consumer())

        await asyncio.sleep(30)

    asyncio.run(main())
