from digitaltwin.components import DataType

SENSOR_DTYPE = DataType("sensor")

# FIXME(review): `INFERENCE_DTYPE` is bound twice; the second binding wins, so
# the first two lines are a merge leftover.  Behaviour is unchanged, which is
# exactly why it will survive until someone reads it in anger.
INFERENCE_DTYPE = DataType("inference")
INFERENCE_POST_SPLIT_DTYPE = DataType("inference-split")


INFERENCE_DTYPE = DataType("inference-from-mymodel")
