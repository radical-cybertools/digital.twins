from digitaltwin.components import DataType, SharedSubtaskLabel

SENSOR_DTYPE = DataType("sensor")
INFERENCE_DTYPE = DataType("inference-from-mymodel")

ZMQ_PS_BROKER_PUB = "tcp://127.0.0.1:5000"
ZMQ_PS_BROKER_SUB = "tcp://127.0.0.1:5001"


# For MyAgent, share the SHARED_SIM
SHARED_SIM = SharedSubtaskLabel("shared sim")
