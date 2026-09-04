from digitaltwin.components import DataType, JoinDataType

# one dtype per persistent sensor in sensors.py
PERSIST_SENSOR_DTYPE = DataType("persist_sensor")
FAST_SENSOR_DTYPE = DataType("fast_sensor")
SLOW_SENSOR_DTYPE = DataType("slow_sensor")
FAST2_SENSOR_DTYPE = DataType("fast2_sensor")
SLOW2_SENSOR_DTYPE = DataType("slow2_sensor")
FAST3_SENSOR_DTYPE = DataType("fast3_sensor")
SLOW3_SENSOR_DTYPE = DataType("slow3_sensor")
FAST4_SENSOR_DTYPE = DataType("fast4_sensor")
SLOW4_SENSOR_DTYPE = DataType("slow4_sensor")

RAND_SENSOR_DTYPE = DataType("rand_sensor")

# input channel and dtype
INPUT_CHANNEL = "test_input"
INPUT_SENSOR_DTYPE = DataType("input_sensor_dtype")


# monitor dtypes

POST_PERSIST_SENSOR = DataType("Post-Persist")
POST_INPUT = DataType("Post-Input")

# model investigator dtypes

INVESTIGATOR_OUT_DTYPE = DataType("investigator_output")

# science agent dtypes

AGENT_OUT_DTYPE = DataType("agent_output")
FLIP_AGENT_IN = DataType("flip_agent_in")
FLIP_AGENT_OUT = DataType("flip_agent_out")

# Data Join Type

DATA_JOIN = JoinDataType([INVESTIGATOR_OUT_DTYPE, AGENT_OUT_DTYPE])

# DATA SPLIT DTYPES

POS_NUM = DataType("pos")
NEG_NUM = DataType("neg")
