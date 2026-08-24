# Service Demo: a digital twin on the ORBIT `dt` plugin

Digital twin application:
- sensor counts to 10 (a persistent component, running inline on the
  service loop and publishing through its injected stream client)
- 1 agent with one investigator
- data sink

Everything except `run_me.py` runs in the service: the client ships the
component *classes* (cloudpickle) and drives the twin with short verbs.

## Running it

Three terminals.  All of them need `pip install .[service]` and the
ORBIT broker cert/token in `~/.radical/orbit/`.

```sh
# 1 - the ORBIT broker, hosting the dt plugin
radical-orbit-broker.py --plugins default,dt

# 2 - a rhapsody endpoint: this is where the twin's tasks execute
RADICAL_ORBIT_RHAPSODY_NOTIFY_WINDOW=0 \
RADICAL_ORBIT_RHAPSODY_BACKEND=concurrent \
radical-orbit-endpoint.py -n dt_task_ep

# 3 - the client
cd test/09-service && python run_me.py
```

`DT_INFERENCE_ENDPOINT` names the endpoint the twin's tasks go to (unset:
ORBIT picks the first endpoint advertising rhapsody).  `DT_SERVICE_HOST`
names the participant hosting the `dt` plugin (default `broker`; set it
to an endpoint name for the endpoint-hosted deployment).

The stream broker is *not* started by hand here: the plugin owns an
embedded one, on a random loopback port, supervised and shared by every
twin.

## Reattaching

The session is persistent and the sid is a bearer capability, so a
client that goes away can come back to its still-running twins:

```python
dt = runtime.get_plugin('broker', 'dt', sid='session.xxxxxxxx')
print(dt.twin_list())
```

`dt.admin_sessions()` lists every session on the service — owner, age,
twins, states and last errors — which is how orphaned sessions are found
and then torn down with the ordinary `twin_close` /
`unregister_session` routes.
