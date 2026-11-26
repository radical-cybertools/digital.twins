from radical.doppelganger.components import DataType

SENSOR_DTYPE = DataType("sensor")
INFERENCE_DTYPE = DataType("inference-from-mymodel")

# the shared channel the external sensor publishes to.  It carries no twin
# namespace: any number of twins may bind it and all of them see every
# message.
SENSOR_CHANNEL = "sensors/latency-probe"
