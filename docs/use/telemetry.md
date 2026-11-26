# Engine-side telemetry

The endpoints record task telemetry on their own (rhapsody's `[telemetry]`
extra).  Only the service's engine sees asyncflow's task lifecycle and
workflow ids, so a session can turn that on as well:

```python
dt = rt.get_plugin('broker', 'dt', config={
    'engines':   {...},
    'telemetry': {'checkpoint_path': '/path/on/service/host'},
})

twin = dt.create_twin(config={'workflow_scope': True})   # or a name
```

`telemetry` is passed to `WorkflowEngine.start_telemetry` and needs the
`service` extra.  The checkpoint is written when the session is
unregistered, and until then events and spans stay in the service's
memory, so this suits bounded runs rather than twins that run for days.
A twin created
with `workflow_scope` tags every task it submits with its id (or the given
name) as `asyncflow.workflow_id`, which is what per-workflow gantt grouping
reads.  A component that opens its own `workflow_scope()` keeps its own id.
