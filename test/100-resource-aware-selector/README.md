

# Resource aware model selection

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
    request profile       Time prediction
                V          |
            +-----------------------+
            | Profile Agent         |
            |  Investigators:       |
            |     Lin Regression    |
            +-----------------------+
```

Now: this assumes there is only one set of endpoints to profile against. One can
have an agent per endpoint to profile. 

> Future changes: 
> Eventually, we would want to add a way to subscribe to ENDPOINT CHANGE events.
> We also want to be able to change the DT Graph as it is running.


### Actual profiler:

I really only need for a single task:
- wall time
- cpu time
- memory
- disk read
- disk write
- net send
- net recv


Options:
- Use AsyncFlow telemetry... (combines metrics of all tasks!)
- Use stand alone profiler exe. Called by executable func.
