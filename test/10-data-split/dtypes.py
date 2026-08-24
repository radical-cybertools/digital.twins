from digitaltwin.components import DataType, JoinDataType

NUMBER_SENSOR_DTYPE = DataType("number")

HIGH_NUMBER_DTYPE = DataType("high-num")
LOW_NUMBER_DTYPE = DataType("low-num")

INFERENCE_DTYPE = DataType("inference")

ZMQ_PS_BROKER_PUB = "tcp://127.0.0.1:5000"
ZMQ_PS_BROKER_SUB = "tcp://127.0.0.1:5001"
