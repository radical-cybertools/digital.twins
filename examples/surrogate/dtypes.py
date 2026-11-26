"""The data types that flow through the twin.

A `DataType` is only a name.  The runtime routes data by it: a component
registered for input `READING` receives every `TypedData(READING, ...)`.
"""

from radical.doppelganger import DataType

# what the sensor measures: a position x in [0, 2*pi)
READING = DataType("reading")

# what the surrogate predicts for a reading
PREDICTION = DataType("prediction")
