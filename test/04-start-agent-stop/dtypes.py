from radical.doppelganger.components import DataType

SENSOR_DTYPE = DataType("sensor")
INFERENCE_DTYPE = DataType("inference-from-mymodel")

# the shared channel the external sensor publishes to
SENSOR_CHANNEL = "sensors/random-walk"
