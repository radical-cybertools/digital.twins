# When an endpoint disappears (R8)

`OrbitExecutionBackend` does not reconnect and components bind their
engine at construction, so a twin whose endpoint went away is stranded
and v1 cannot heal it.  It is at least not silent: the plugin watches
the ORBIT topology and marks every twin that bound an engine on a lost
endpoint `failed`, with `engine endpoint lost: <endpoint>` in
`twin_list`.  Twins on surviving engines keep running.

Recovery means **closing the session**, not just the twins: engines are
session-shared, so a twin created afterwards would inherit the dead one.
The session remembers the loss and refuses to hand that engine out
again, so a `twin_create` after it fails immediately with `engine
'<name>' endpoint was lost; recreate the session` rather than coming up
`ready` and stalling.  `unregister_session`, then build the session and
its twins again.
