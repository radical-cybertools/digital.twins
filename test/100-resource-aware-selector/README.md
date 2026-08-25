

# Resource aware model selection for inference.

One of the requirements of the digital twin is to dynamically select the
appropriate endpoints to run an inference task, balancing predicted accuracy
against compute time.

The way the DT Framework is designed is to provide simply a set of abstractions
(agents, investigators, etc...). So, to support resource-aware selection, the
user must create their own logic. 

This example demonstrates how to create an agent specifically for profiling
tasks. Then, the primary agent simply calls this agent to get a resource profile
measurement. 


DT Graph:

```
           +-----------------------+
Sensor --> | Agent                 |  ---> Sink
           |  Investigators:       |
           |     - Positive Model  |
           |     - Negative Model  |
           +-----------------------+
```

Now, adding in a resource profiler agent:

```
           +-----------------------+
Sensor --> | Agent                 |  ---> Sink
           |  Investigators:       |
           |     - Positive Model  |
           |     - Negative Model  |
           +-----------------------+
                |          ^
    request profile       Time prediction -----+
                V                              |
            +-----------------------+          |
            | Profile Investigator  |          |
            |  Profiler on          |          |
            |  dedicated machine    |          |
            +-----------------------+          |
                |                              |
    request endpoint-adjusted       +----------+
            profile                 |
                |                  Time Prediction
                V                   |
            +-------------------------+
            | Endpoint Investigator   |
            |  Sim: endpoint profiler |
            |  Train: XGBRegressor    |
            +-------------------------+       
```

Now: this assumes there is only one set of endpoints to profile against. One can
have an agent per endpoint to profile. 

> Future changes: 
> Eventually, we would want to add a way to subscribe to ENDPOINT CHANGE events.
> We also want to be able to change the DT Graph as it is running.


## How to run:
1. For demo, copy `profiler/pi_profiler/data.csv.sample` to just
`profiler/pi_profiler/data.csv`
2. Ensure pip packages are installed (example uses xgboost and sklearn)
3. Start a local_broker.py in a separate terminal
4. Run `run_me.py` in this directory.

## Structure:

The files in `profiler/` consist of the profiler itself, a surrogate predictor,
and the investigators. The "simulation" in this case is an actual task profiler.

The profiler is in:
- `profiler.py` <-- runs the measurements
- `executor.py` <-- runs the python function

The prediction model is an XGBRegressor
- `endpoint_eval.py` <-- inference
- `endpoint_trainer.py` <-- train
- `profiling.ipynb` <-- visualizations

Now, for the model to work effectively, it needs a prior dataset to train on.
- `pi_profiler/data.csv.sample` is a sample dataset
- `capture.sh` allows for conducting your own profiling. 
- `stress_tests` is a repository consisting of multiple stress tests. These were
  used to create the sample dataset. (See README inside it).

To build your own dataset manually:
1. Run `capture.sh dedicated.csv` on the dedicated profiling instance.
2. Run `capture.sh endpoint.csv` on the endpoint you want to build a prediction model for.
3. Copy the "t_seconds" `endpoint.csv` into a new column named "pi_seconds" in
   the dedicated.csv. This is the new dataset.



