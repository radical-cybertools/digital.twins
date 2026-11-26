# Watching it run: the dashboard

`src/radical/doppelganger/service/ui/` holds a dependency-free canvas dashboard
(one JS file, no build step) that draws the service as role lanes: the
**client** with a sub-lane per session, the **sensors** below it, the
**broker** with one card per twin -- short uuid, colour-coded state,
namespace, stream-backend badge, and a convergence bar per learner metric
-- and, grouped under an *HPC resources* frame, the **task** and
**ex-situ endpoint** lanes where the twins' simulation tasks appear as
tiles.  The lanes are roles, not hosts: a single-endpoint deployment
still gets both endpoint lanes, and the ex-situ one is labelled
`aliases task`.

The sensors lane is observed, not declared: every `dt_stream` topic names
a twin and a dtype, and only a twin's own persistent components publish,
so one tile per `(twin, dtype)` *is* the set of sensors.  It sits outside
the broker frame because that is where a reader looks for where data
comes from, and it says `in the plugin host`, because in v1 that is where
those components run.

Three ways to open it, in increasing order of what they need:

```sh
# 1 - offline: replay the recording bundled in the repo, no stack at all
xdg-open src/radical/doppelganger/service/ui/index.html

# 2 - live, served by the broker itself (the only way live works -- see below)
xdg-open https://<broker>/broker/dt/ui

# 3 - live, inside the ORBIT Explorer: open https://<broker>/ and pick the
#     'Digital Twins' plugin.  The plugin ships the page as its `ui_module`;
#     nothing to install
```

**Live mode has to be same-origin with the broker.** The gateway's CORS
allow-list holds a handful of `localhost` origins, and the
`orbit_broker_token` cookie that the `EventSource` rides is
`SameSite=Strict` -- so a page opened from anywhere else cannot reach a
live broker even with the right token.  Served from the broker there is
no cross-origin request at all.  The broker's certificate is self-signed:
visit `https://<broker>/` once and accept it, which is also where the
token is entered (that mints the cookie the dashboard then reuses).
Everything else -- replaying a recording, loading one by drag-and-drop --
works from `file://` with no server.

The data layer treats live and replayed input identically: a stream of
timestamped frames, either an `admin/sessions` poll at 1 Hz plus the
gateway's SSE feed, or the same frames read back from a recording.  So
`rec` captures the live stream to a JSON file, `load…` (or a drop on the
canvas) replays one, and the play/pause and speed controls act on the
data rather than on an animation.  The schema is documented at the top of
`dt_dash.js` and checked by `test/unit/test_ui_recording.py`.

One thing the picture makes obvious once it is drawn: **the runtime never
publishes a component's answer**.  An inference result goes to the next
component on that dtype over an in-process queue, and is dropped if
nothing is registered there.  For anything outside the service to see a
result, a component has to publish it (`EchoSink` in the demos does
exactly that, which is why the sensors lane shows a twin's results as
well as its readings), and the client then subscribes to the twin's
stream with the `PubSubConfig` the twin reports.  A client's own
`get_inference` is the other path, and the only one that answers the
caller directly.

If the dashboard does not look like this, check the version the header
draws next to the stream pill against `VERSION` in `dt_dash.js`.  A
browser keeps a `file://` script well past the edit that changed it (hence
the `?v=` on the page's script tags), and the copy the broker serves is
the *installed* one -- as new as the last `pip install .`, no newer.

The Explorer integration is broker-hosted only.  ORBIT reads `ui_module`
in `BrokerPluginHost.get_ui_modules()` and nowhere else, so an
endpoint-hosted `dt` plugin gets the declarative `ui_config` tile and no
dashboard page; `{namespace}/ui` still serves it directly.  The gateway
also caches a plugin's JS for the life of the broker process, so editing
`dt_explorer.js` needs a restart -- `{namespace}/ui/dt_dash.js`, which
the plugin serves itself, does not.
