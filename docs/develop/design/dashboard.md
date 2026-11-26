# Dashboard internals

How the dashboard derives what it draws.  For using it, see
[Watching it run](../../use/dashboard.md).

Three things the dashboard reads that nothing else needed.  `twin_list`
and `admin/sessions` carry a per-twin `metrics` dict -- a filtered,
read-only view of a learner's per-window criterion (`value`, `threshold`,
`operator`, `should_stop`, window count and a bounded history), never the
model itself -- a per-twin `tasks` list of the uids that twin most
recently submitted, and a per-session `endpoints` map naming the hardware
behind each engine role.  (The per-twin `calls` count per verb is there
too, for observers; the dashboard no longer draws it.)

Everything reads on the cards and lanes in place: a twin card's state
pill and transition markers, its components and metrics, the channels
lane's per-dtype counts, and each endpoint lane's task chart and
recent-task table.  The dashboard used to animate arcs for creates, state
reports, client calls, stream samples and tasks; they added motion but no
information the cards did not already show, and they are gone.

**Tasks are attributed to the twin that submitted them**, and that is
known rather than guessed: a `task_status` notification carries a uid and
an endpoint and nothing else, so ownership is recorded where the
submission happens.  asyncflow assigns each task a uid (`task.NNNNNN`) in
the component description and rhapsody's backend keeps it, which is the
same uid the notification carries -- so the twin remembers the uids it
submitted (`DTRuntime.note_task`, a ring of the newest `TASK_UID_RING`),
`twin_list` carries them as `tasks`, and the dashboard joins on them.
Two paths reach that ring: the runtime records the future it is about to
await, and -- because a real inference task is usually a plain coroutine
that awaits a flow task the runtime never sees -- the engine's own
component registration is wrapped, with the owning twin carried in a
`ContextVar` that asyncio copies into every task underneath.  ROSE's
ex-situ tasks are the third case: `Learner._register_task` is wrapped per
instance in `StreamingLearnerInvestigator.main_loop`, where the runtime is
in hand, so training, active learning and the criterion are the twin's too
without ROSE changing.

A notification beats the 1 Hz poll that explains it, so a finished task
keeps its tile for up to `OWNER_WAIT` while the join lands, and after that
claims no owner.  The lane is a per-session answer too (one endpoint can
be one session's task engine and another's ex-situ engine), and an
endpoint no session of ours declared is another deployment's, so its
tasks are drawn on neither lane.

A twin that leaves `twin_list` keeps its card for nine seconds, dimmed,
with the last state pill the service reported and a `closed` mark, then
fades: a run that ends by closing its twins would otherwise erase the
evidence a second later.  A lingering card yields its grid slot to a live
twin if the lane runs out of room.
