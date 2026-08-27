import json
import os
import subprocess
import sys

from digitaltwin.components import DataType, TypedData
from profiler import export_inference_function

test_dtype = DataType("test")


async def my_func(in_data: TypedData, model=123):
    print(in_data.data)
    a = 0
    for i in range(10_000_000):
        a += i % 42
    # with open("/tmp/test.txt", "w") as f:
    #     f.write("Hello!" * 4096)
    with open("/tmp/test.txt", "r") as f:
        print(f.read())
    print(a)


export_inference_function(
    "test1.pkl", my_func, TypedData(test_dtype, "hello"), model=123
)


profiler = subprocess.Popen(
    [
        sys.executable,
        os.path.join(os.path.dirname(__file__), "profiler.py"),
        "test1.pkl",
    ],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.PIPE,
)

p_out = profiler.communicate()

if profiler.returncode != 0:
    raise ValueError("Profiler returned non zero!")

r = json.loads(p_out[0].decode())

print(r)
