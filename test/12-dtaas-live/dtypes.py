"""The dtypes this demo's twins are wired with.

Shipped to the service by value along with the components -- the service
has no copy of this directory.
"""

from digitaltwin.components import DataType

SENSOR_DTYPE = DataType("sensor")
INFERENCE_DTYPE = DataType("inference")

# What a twin's own results are published under, so the dashboard's
# sensors lane shows answers as well as readings.  The runtime never
# publishes a component's return value by itself -- a component has to.
RESULT_CHANNEL = "results"
