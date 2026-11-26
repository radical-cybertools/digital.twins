# Run the twin on the service

The twin from [Your first twin](first-twin.md) runs unchanged on a DTaaS
service.  This page brings up a complete service on one machine, runs
the example against it, and then shows what changes for a remote broker
and HPC endpoints.

It needs the `service` and `learn` extras on every host (see
[Install](install.md)).

## The parts

| Part | Command | Role |
|---|---|---|
| broker | `radical-orbit-broker.py --plugins default,dt` | hosts the `dt` plugin; twins live here |
| endpoint | `radical-orbit-endpoint.py -n <name>` | runs the twins' tasks |
| client | `python run_service.py` | ships the components and drives the twin |

The broker and endpoints come from ORBIT.  The
[ORBIT getting-started guide](https://radicalorbit.readthedocs.io/en/latest/getting_started/)
covers their configuration in full; the steps below are the minimum.

## 1. Certificate and token, once

The broker serves TLS and admits only holders of its token.  For a
single development machine:

```sh
mkdir -p ~/.radical/orbit && cd ~/.radical/orbit
openssl req -x509 -newkey rsa:4096 -nodes -days 365 \
    -keyout broker_key.pem -out broker_cert.pem \
    -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
chmod 600 broker_key.pem
python3 -c "import secrets; print(secrets.token_urlsafe(32))" > broker.token
chmod 600 broker.token
```

Clients and endpoints on other hosts need the certificate and the token,
never the key.

Every process (broker, endpoints, client) also needs the broker's URL.
Set it in each terminal:

```sh
export RADICAL_ORBIT_BROKER_URL=https://localhost:8000
```

or write it once to `~/.radical/orbit/broker.url`.  The broker needs it
too: with `DT_STREAM_BACKEND=orbit` the `dt` plugin connects back to the
broker for the twins' streams, and a twin fails to initialize with
`Broker URL required` without it.

## 2. Start a broker and an endpoint

In two terminals, each with `RADICAL_ORBIT_BROKER_URL` set:

```sh
# terminal 1: the broker, hosting the dt plugin
DT_STREAM_BACKEND=orbit radical-orbit-broker.py --plugins default,dt

# terminal 2: an endpoint that runs the twin's tasks
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
radical-orbit-endpoint.py -n local_ep
```

`DT_STREAM_BACKEND=orbit` carries the twin's streams over the broker's
authenticated connection (see [Choosing a data plane](../use/data-plane.md)).
`RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0` matters for in-situ inference:
the default batches task notifications and adds 250 ms to every
prediction.

## 3. Run the client

In a third terminal, also with `RADICAL_ORBIT_BROKER_URL` set:

```sh
cd examples/surrogate
DT_INFERENCE_ENDPOINT=local_ep python run_service.py
```

The output matches the local run, with the session id first.

## What the client does

```python
--8<-- "examples/surrogate/run_service.py:main"
```

Compared with `run_local.py`:

- `register_user_modules([...])` ships the example's modules by value.
  The service does not have your code; this is how it gets it.
- `dt.package(Cls, *args)` wraps a component class and its constructor
  arguments.  The service instantiates it with its own engine.
- Every runtime call takes the twin id as its first argument.
- The session outlives the client.  `unregister_session()` ends it and
  its twins; without it the twin keeps running, and
  `runtime.get_plugin('broker', 'dt', sid=<sid>)` reattaches later.

The [Service guide](../use/service.md) documents every call.

## Two endpoints: inference and learning

A session names the endpoint for each role.  `run_service.py` builds
this configuration from the environment:

```python
--8<-- "examples/surrogate/run_service.py:config"
```

Start a second endpoint and point the learning role at it:

```sh
# terminal 3
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
radical-orbit-endpoint.py -n learn_ep

# the client
DT_INFERENCE_ENDPOINT=local_ep DT_LEARNING_ENDPOINT=learn_ep python run_service.py
```

The learner's training, active-learning and criterion tasks now run on
`learn_ep`, and inference stays on `local_ep`.  On a real deployment
`learn_ep` is an endpoint on an HPC allocation.

## A remote broker and HPC

Nothing in the client changes.  Point it at the broker and give it the
broker's certificate and token:

```sh
export RADICAL_ORBIT_BROKER_URL=https://<broker-host>:8000
scp <broker-host>:.radical/orbit/broker_cert.pem <broker-host>:.radical/orbit/broker.token ~/.radical/orbit/
```

An endpoint on an HPC machine is started the same way, on a compute node
of an allocation, with the same three files.  For NERSC Perlmutter with
Dragon, `use-cases/dt-complete/deploy/` in
[radical-collaboration/amsc](https://github.com/radical-collaboration/amsc)
has tested scripts and the constraints they encode.

Every host must run the same `radical.doppelganger`, Python minor and
cloudpickle versions; the service refuses a mismatch on the first call.
