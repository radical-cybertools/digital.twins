/* ==========================================================================
 *  dt_dash.js -- a live / replayable dashboard for the DTaaS `dt` plugin
 *
 *  One implementation, two hosts:
 *
 *    - standalone: `index.html` loads this file with a plain <script src>
 *      and calls `DTDash.mount(el, opts)`.
 *    - ORBIT Explorer: `dt_explorer.js` (the plugin's `ui_module`) pulls
 *      this same file in with a dynamic `import()` and calls the same
 *      `mount()`.  The file has no imports and no exports, so it is valid
 *      as a classic script *and* as an ES module; it publishes itself on
 *      `window.DTDash` either way.
 *
 *  Zero dependencies, no build step.  Everything is drawn on one canvas,
 *  which is resolution-adaptive (ResizeObserver + devicePixelRatio): the
 *  layout is recomputed from the container's size on every frame, because
 *  this has to be legible both full-screen and inside an Explorer page.
 *
 *  ------------------------------------------------------------------------
 *  DATA SOURCES (live mode)
 *
 *    GET  {broker}{dtPath}/admin/sessions   -- polled at 1 Hz
 *         Every session (sid, owner, age, engines, engine endpoints) and
 *         every twin (twin_id, state, last_error, age, metrics), plus the
 *         data plane's backend.  This is the ground truth for the lanes,
 *         the twin cards and the convergence bars.  `dtPath` defaults to
 *         `/broker/dt` -- the gateway's proxy path for a broker-hosted
 *         `dt` plugin.
 *
 *    GET  {broker}/events                   -- EventSource
 *         Frames are `{topic:'notification', data:{endpoint, plugin,
 *         topic, data}}`.  The gateway fans every event to every SSE
 *         client, so the filtering is ours:
 *           plugin 'rhapsody', topic 'task_status' / 'task_status_batch'
 *             -> simulation task tiles on the endpoint lane named by
 *                `endpoint` (states RUNNING / DONE / FAILED / CANCELED);
 *           plugin 'dt_stream' (only under DT_STREAM_BACKEND=orbit)
 *             -> a stream pulse on the twin named by the DT topic
 *                `dt/<twin_id>/dtypes/<label>`.
 *
 *    POST {broker}/auth                     -- once, with a bearer token
 *         Mints the `orbit_broker_token` cookie that the EventSource rides
 *         (EventSource cannot carry headers).
 *
 *  The create / destroy / state-change verbs are *inferred* from the delta
 *  between two consecutive polls: nothing on the wire announces them in
 *  v1, and `twin_list` polling is the documented observation mechanism.
 *
 *  ------------------------------------------------------------------------
 *  RECORDING SCHEMA  ("dt-dash-recording/1")
 *
 *    {
 *      "schema":   "dt-dash-recording/1",
 *      "recorded": "<ISO 8601 UTC>",    // when the capture started
 *      "broker":   "<broker url>",      // provenance; unused on replay
 *      "duration": <seconds>,           // `t` of the last frame
 *      "frames": [
 *        {"t": <seconds since capture start>,
 *         "kind": "snapshot",           // one admin/sessions response
 *         "data": {"sessions": [...], "stream_broker": {...}}},
 *        {"t": <seconds>,
 *         "kind": "event",              // one SSE notification, inner
 *         "data": {"endpoint": "...", "plugin": "...", "topic": "...",
 *                  "data": {...}}}
 *      ]
 *    }
 *
 *  Frames are ordered by `t`.  A replay hands the model exactly the frames
 *  a live session would have handed it, in the same order, which is why
 *  there is one model and not two.  A *recording* holds each payload minus
 *  the fields nothing here reads -- a task's return value, a stream
 *  message's cloudpickled body -- because on a long capture those are most
 *  of the bytes; `captureFrame` below is the one place that decides it.
 *  `test/unit/test_ui_recording.py` checks the bundled sample against this
 *  schema, so the two stay in sync.
 * ========================================================================*/

(() => {

  const VERSION = '0.7.0';
  const SCHEMA  = 'dt-dash-recording/1';

  // -------------------------------------------------------------------------
  //  Palette + fonts.  Borrowed from the deck's flow diagrams so the panel
  //  idiom feels native next to the slides:
  //    frame_border = inner-node stroke, frame_label = node title.
  // -------------------------------------------------------------------------
  const FONT      = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  const FONT_MONO = "ui-monospace, 'SF Mono', Menlo, Consolas, monospace";

  const C = {
    bg:           '#080818',
    panel:        '#0d1525',
    panel_deep:   '#0a1120',
    frame_border: '#1e3a5f',
    frame_label:  '#94a3b8',
    text:         '#e6ecf6',
    text_dim:     '#7080a0',
    text_label:   '#a0b0c8',
    cyan:         '#40c8e8',
    amber:        '#e8a040',
    green:        '#5acd83',
    // the deck's AsyncFlow level colour (docs/dtaas-architecture.svg): a
    // task result comes back *through* the engine, so it is drawn in the
    // engine's own colour and not in the stream green it used to share
    violet:       '#a78bfa',
    red:          '#e8556a',
    grey:         '#5a6478',
    cyan_dim:     '#15384a',
    amber_dim:    '#4a3418',
    green_dim:    '#1a4028',
    grey_dim:     '#222a38',
    unused:       '#161e2a',
    unused_brd:   '#283040',
  };

  // the plan's twin state machine, plus the service's terminal `closed`
  const STATE_COLOR = {
    initializing: C.amber,
    ready:        C.cyan_dim,
    running:      C.cyan,
    stopped:      C.grey,
    closed:       C.grey,
    failed:       C.red,
  };
  const STATE_TEXT = {
    initializing: C.amber,
    ready:        C.cyan,
    running:      C.cyan,
    stopped:      C.text_dim,
    closed:       C.text_dim,
    failed:       C.red,
  };

  // rhapsody task states that actually reach a browser.  There is no
  // QUEUED: the only non-terminal state any backend pushes is RUNNING.
  const TASK_TERMINAL = new Set(['DONE', 'FAILED', 'CANCELED', 'COMPLETED']);

  // -------------------------------------------------------------------------
  //  Timings, in seconds of *model* time (the replay speed scales them all)
  // -------------------------------------------------------------------------
  const POLL_INTERVAL = 1.0;    // admin/sessions poll period, live mode
  const POLL_TIMEOUT  = 10.0;   // and the deadline on one such request
  const FLIGHT        = 1.0;    // create / destroy / spawn arc duration
  const FADE          = 0.9;    // completed task tile fade-out
  const MARKER_TTL    = 2.6;    // state-transition marker lifetime
  const PULSE_TTL     = 0.7;    // stream pulse ring lifetime
  const GLOW          = 0.5;    // on-landing halo
  const PULSE_FLIGHT  = 0.5;    // sensor sample / task result hop
  const CALL_ARCS_MAX = 3;      // client-call arcs drawn per poll per verb
  const GONE_LINGER   = 9.0;    // a closed twin's card stays this long
  const GONE_FADE     = 3.6;    // ... fading out over the last of it
  const OWNERS_MAX    = 4000;   // uid -> twin entries kept from the polls
  const OWNER_WAIT    = 2.2;    // ... and how long a task waits for its own
  const CARD_ANCHOR   = 0.67;   // where down a card its arcs meet it
  const SPARK_MAX     = 24;     // sparkline points kept per metric
  const TASK_MAX      = 400;    // tile slots per endpoint lane
  const TASK_TTL      = 300;    // drop a task nothing has mentioned since
  const CAPTURE_MAX   = 4000;   // frames one `rec` may hold
  const SSE_BACKOFF   = 30;     // longest wait before re-opening the feed

  // =========================================================================
  //  MODEL -- frames fold into one world; nothing here knows live from replay
  // =========================================================================

  function newWorld() {
    return {
      t:         0,         // model clock, seconds
      backend:   null,      // 'zmq' | 'orbit' | null (nothing seen yet)
      stream:    null,      // the stream_broker summary, verbatim
      sessions:  [],        // [{sid, owner, age, engines, twins, _rect}]
      twins:     new Map(), // twin_id -> twin
      endpoints: { inference: [], learning: [], alias: true },
      roles:     new Map(), // endpoint -> Set('inference'|'learning')
      tasks:     new Map(), // uid -> {uid, lane, state, t0, tEnd, slot}
      // task uid -> twin_id, straight off the twins' own `tasks` lists: the
      // service records what it submitted, so this is the whole of the
      // dashboard's task attribution -- nothing here guesses any more
      owners:    new Map(),
      counts:    { inference: zeroCount(), learning: zeroCount() },
      flights:   [],
      markers:   [],
      snapshots: 0,
      events:    0,
      reported:  null,      // model time of the last state listing
      probe:     null,      // {t, twin} of the last get_inference served
      // '<twin>|<dtype>' -> {twin, dtype, t, count}: every stream
      // publisher we have seen, which is what the sensors lane draws
      publishers: new Map(),
      // Per-pool event log for the task-manager graph.  A sequence of
      // `{t, running}` samples pushed whenever the concurrent count
      // changes -- so between events the value is exactly the running
      // count that held over that interval, and the graph reads the
      // true concurrent count at every instant of the visible window.
      poolHistory: { inference: [], learning: [] },
    };
  }

  function zeroCount() { return { running: 0, done: 0, failed: 0 }; }

  function ingest(w, frame) {
    if (frame.kind === 'snapshot') applySnapshot(w, frame.data);
    else if (frame.kind === 'event') applyEvent(w, frame.data);
  }

  // ---- snapshots: admin/sessions, and the verbs it implies ----------------

  function applySnapshot(w, snap) {
    if (!snap || typeof snap !== 'object') return;

    w.snapshots++;

    const broker = snap.stream_broker || {};
    w.stream  = broker;
    w.backend = broker.backend || w.backend;

    const sessions = Array.isArray(snap.sessions) ? snap.sessions : [];
    const seen = new Set();

    // when this listing arrived: every poll reports every session's twins,
    // so one timestamp covers all of them (see the tick in the client lane)
    w.reported = w.t;

    w.sessions = sessions.map(s => ({
      sid:      s.sid || '?',
      owner:    s.owner || null,
      age:      num(s.age),
      lifetime: s.lifetime || null,
      active:   s.active !== false,
      engines:  Array.isArray(s.engines) ? s.engines : [],
      // the engine-role -> endpoint map; `laneOf` reads it per session
      endpoints: s.endpoints || {},
      twins:    (s.twins || []).map(t => t.twin_id),
    }));

    // Engine endpoints.  The lanes are *roles*, and which endpoint serves
    // which role is a per-session answer: a lane therefore names every
    // endpoint any session put in that role, and `roles` is the reverse map
    // `laneOf` falls back on when a task's owner is not known yet.  A
    // deployment that configured no ex-situ engine still gets two lanes --
    // the ex-situ one then says it aliases the task one, which is the truth
    // on the wire.
    const inference = [], learning = [];
    let sawLearning = false;
    w.roles = new Map();

    for (const s of sessions) {
      const eps = s.endpoints || {};
      for (const role of ['inference', 'learning']) {
        const name = eps[role];
        if (!name) continue;
        if (role === 'learning') sawLearning = true;
        const into = role === 'inference' ? inference : learning;
        if (!into.includes(name)) into.push(name);
        if (!w.roles.has(name)) w.roles.set(name, new Set());
        w.roles.get(name).add(role);
      }
    }
    w.endpoints = { inference, learning,
                    alias: sessions.length > 0 && !sawLearning };

    for (const s of sessions) {
      for (const t of (s.twins || [])) {
        const id = t.twin_id;
        if (!id) continue;
        seen.add(id);
        upsertTwin(w, s, t);
      }
    }

    // the poll may be exactly the one a task's arcs were waiting for
    armTasks(w);

    for (const [id, tw] of w.twins) {
      if (seen.has(id) || tw.gone !== null) continue;
      tw.gone = w.t;
      flight(w, 'destroy', { twin: id });
      marker(w, id, 'closed', C.grey);
    }
  }

  function upsertTwin(w, s, t) {
    const id = t.twin_id;
    let tw = w.twins.get(id);

    if (!tw) {
      tw = {
        id, sid: s.sid, state: t.state, born: w.t, fresh: w.t, tState: w.t,
        last_error: null, age: null, metrics: {}, spark: new Map(),
        pulse: null, gone: null,
      };
      w.twins.set(id, tw);
      // A twin that was already there when we attached is not a `create`
      // we witnessed: only the ones appearing in a *later* poll get an arc.
      if (w.snapshots > 1) {
        flight(w, 'create', { twin: id });
        marker(w, id, 'create', C.cyan);
      }
    } else if (tw.state !== t.state) {
      tw.prev   = tw.state;
      tw.tState = w.t;
      marker(w, id, t.state, STATE_TEXT[t.state] || C.text_dim);
      // The state going back the other way.  Same inferred fidelity as
      // the create / destroy arcs: what the client actually receives is a
      // `twin_list` response, and this is the transition inside it.
      flight(w, 'report', { twin: id, label: t.state });
    }

    tw.sid        = s.sid;
    tw.state      = t.state;
    tw.last_error = t.last_error || null;
    tw.age        = num(t.age);
    tw.gone       = null;
    applyMetrics(tw, t.metrics);
    applyCalls(w, tw, t.calls);
    applyTasks(w, id, t.tasks);
  }

  // The twin's own record of what it submitted (`TASK_UID_RING` in the
  // service).  Kept cumulatively here, because the service's ring only has
  // to cover a poll period while this map has to outlive the task: an event
  // arriving before the poll that explains it draws from the broker's edge
  // and snaps to the card on the next frame, which is the whole of the join.
  function applyTasks(w, id, uids) {
    if (!Array.isArray(uids)) return;

    for (const uid of uids) {
      if (typeof uid === 'string') w.owners.set(uid, id);
    }

    // bounded, and insertion-ordered, so the oldest uid goes first
    while (w.owners.size > OWNERS_MAX) {
      w.owners.delete(w.owners.keys().next().value);
    }
  }

  // A twin's `metrics` entry is the service's filtered, read-only view of
  // the ROSE learner's per-window criterion state.  The learner carries a
  // history; where it does not, we accumulate what we observe, so a metric
  // always has a sparkline.
  function applyMetrics(tw, metrics) {
    if (!metrics || typeof metrics !== 'object') return;

    tw.metrics = metrics;

    for (const [name, m] of Object.entries(metrics)) {
      if (!m || typeof m.value !== 'number') continue;
      let hist = tw.spark.get(name);
      if (!hist) { hist = []; tw.spark.set(name, hist); }

      const given = Array.isArray(m.history) ? m.history : null;
      if (given && given.length >= hist.length) {
        hist.length = 0;
        for (const v of given.slice(-SPARK_MAX)) hist.push(v);
      } else if (hist[hist.length - 1] !== m.value) {
        hist.push(m.value);
        if (hist.length > SPARK_MAX) hist.shift();
      }
    }
  }

  // The service counts each verb it answered per twin.  The difference
  // between two polls is a number of completed round trips: a request that
  // reached the twin and an answer that went back.  That is all a client
  // call leaves behind -- the verbs are synchronous and nothing is pushed
  // -- so this is the only honest source for the two client-ward arcs.
  function applyCalls(w, tw, calls) {
    if (!calls || typeof calls !== 'object') return;

    const before = tw.calls || {};

    for (const [verb, count] of Object.entries(calls)) {
      const delta = count - (before[verb] || 0);
      // the first poll of an already-busy twin is a total, not a burst
      if (delta <= 0 || !tw.calls) continue;

      for (let i = 0; i < Math.min(delta, CALL_ARCS_MAX); i++) {
        flight(w, 'call', { twin: tw.id, label: verb });
        // only `get_inference` carries an answer worth drawing; the rest
        // return a state a client does not wait on
        if (verb === 'get_inference') {
          // after the request, not with it: one round trip, drawn as one
          flight(w, 'answer', { twin: tw.id, delay: FLIGHT * 0.6 });
          // and the beat in which the twin was serving a probe.  A twin
          // answers `get_inference` by running its investigator's inference
          // task, which is a *task-engine* task -- the ex-situ engine only
          // ever gets training windows.  Which tile that was cannot be
          // known (a `task_status` carries no verb), so
          // the task lane says only when, and says it dimly.
          w.probe = { t: w.t, twin: tw.id };
        }
      }
    }

    tw.calls = calls;
  }

  // ---- events: rhapsody task status, and DT stream pulses -----------------

  function applyEvent(w, ev) {
    if (!ev || typeof ev !== 'object') return;
    w.events++;

    const plugin = ev.plugin || '';
    const topic  = ev.topic  || '';
    const data   = ev.data   || {};

    if (topic === 'task_status') {
      applyTask(w, ev.endpoint, data);
    } else if (topic === 'task_status_batch') {
      for (const t of (data.tasks || [])) applyTask(w, ev.endpoint, t);
    } else if (plugin === 'dt_stream') {
      applyStream(w, topic);
    }
  }

  // Which role lane an endpoint belongs to, for *this* task.  Roles, not
  // hosts: one endpoint can be the task engine of one session and the
  // ex-situ engine of another, so the owning twin's session decides it, and
  // only when the owner is unknown does the aggregate have to answer.
  //
  // An endpoint no session of ours declared is not ours: the gateway fans
  // every rhapsody event to every SSE client, so those belong to another
  // deployment and `null` keeps them off both lanes.  Under an aliased
  // deployment both roles name the same endpoint and everything lands on
  // `task`, which is what the ex-situ lane's own label says.
  function laneOf(w, endpoint, twinId) {
    if (!endpoint) return null;

    const tw = twinId && w.twins.get(twinId);
    const own = tw && w.sessions.find(s => s.sid === tw.sid);

    if (own) {
      const eps = own.endpoints || {};
      if (eps.learning === endpoint) return 'learning';
      if (eps.inference === endpoint) return 'inference';
    }

    const roles = w.roles.get(endpoint);
    if (!roles) return null;

    return roles.has('inference') ? 'inference' : 'learning';
  }

  function applyTask(w, endpoint, t) {
    const uid = t && t.uid;
    if (!uid) return;

    const state = String(t.state || 'RUNNING').toUpperCase();
    let task = w.tasks.get(uid);

    if (!task) {
      const lane = laneOf(w, endpoint, w.owners.get(uid));
      if (!lane) return;                 // an endpoint no session of ours has
      task = { uid, lane, state, t0: w.t, seen: w.t, tEnd: null,
               slot: nextSlot(w, lane),
               // when its arcs left, and when the returning one is due:
               // both wait for the poll that says whose task this is
               armed: null, due: null };
      w.tasks.set(uid, task);
      w.counts[lane].running++;
      recordPoolEvent(w, lane);
      armTasks(w);
    }

    // every mention refreshes it, repeated states included: a task is
    // aged out on *silence*, and a batch flush re-stating RUNNING is not
    // silence (see `expire`)
    task.seen = w.t;

    if (task.state !== state) {
      task.state = state;
      if (TASK_TERMINAL.has(state)) {
        task.tEnd = w.t;
        const c = w.counts[task.lane];
        c.running = Math.max(0, c.running - 1);
        if (state === 'FAILED') c.failed++;
        else if (state !== 'CANCELED') c.done++;
        // the compute coming back: a real observed transition, and the
        // only half of the round trip that was missing
        task.due = w.t;
        recordPoolEvent(w, task.lane);
        armTasks(w);
      }
    }
  }

  // Event-driven graph record.  Called whenever the running count for a
  // pool actually changes.  Old entries beyond the visible window are
  // pruned lazily on each push, keeping the newest one older than the
  // cutoff so the left edge of the graph knows what value to start at.
  function recordPoolEvent(w, lane) {
    const hist = w.poolHistory[lane];
    hist.push({ t: w.t, running: w.counts[lane].running });
    const cutoff = w.t - POOL_WINDOW - 2;
    let keepFrom = -1;
    for (let i = 0; i < hist.length; i++) {
      if (hist[i].t <= cutoff) keepFrom = i;
      else break;
    }
    if (keepFrom > 0) hist.splice(0, keepFrom);
  }

  // A task's arcs wait for the poll that says whose it is.  The notification
  // beats that poll by up to a full period -- the task is submitted, ORBIT
  // reports it running within milliseconds, and `admin/sessions` is only
  // sampled at 1 Hz -- so an arc drawn on arrival would leave the broker's
  // edge for want of a join that is about to land.  It waits, and after
  // `OWNER_WAIT` it goes anyway, from the edge, claiming nothing.
  function armTasks(w) {
    for (const t of w.tasks.values()) {
      const known = w.owners.has(t.uid);

      if (t.armed === null && (known || w.t - t.t0 > OWNER_WAIT)) {
        t.armed = w.t;
        flight(w, 'spawn', { task: t });
      }

      if (t.due !== null && t.armed !== null
          && (known || w.t - t.due > OWNER_WAIT)) {
        t.due = null;
        flight(w, 'result', { task: t, dur: PULSE_FLIGHT });
      }
    }
  }

  // Slots are claimed per lane and held for the task's lifetime, so a
  // running tile never hops while its neighbours come and go.
  function nextSlot(w, lane) {
    const used = new Set();
    for (const t of w.tasks.values()) if (t.lane === lane) used.add(t.slot);
    for (let i = 0; i < TASK_MAX; i++) if (!used.has(i)) return i;
    return 0;
  }

  // `dt/<twin_id>/dtypes/<label>`: the DT topic is the ORBIT topic
  // verbatim under the orbit data-plane backend, so a pulse is
  // attributable to the exact twin and dtype that produced it.  The label
  // carries `PubSubClient.TOPIC_TERMINATOR` -- a NUL, there to stop ZMQ's
  // prefix matching from confusing two labels that share a prefix.
  function applyStream(w, topic) {
    const parts = String(topic).split('/');
    if (parts.length < 4 || parts[0] !== 'dt') return;

    const id = parts[1];
    const dtype = parts[3].replace(/\0+$/, '');
    const tw = w.twins.get(id);
    if (!tw) return;

    tw.pulse = { t: w.t, label: dtype };

    // One publisher per dtype: multiple twins that emit the same channel
    // share a row.  Counts and last-seen aggregate across them; `twin`
    // records whichever twin last pulsed so the (now-muted) sample arc
    // still resolves an origin twin if anything asks.
    const key = dtype;
    let pub = w.publishers.get(key);
    if (!pub) {
      pub = { key, dtype, count: 0, t: w.t, twin: id };
      w.publishers.set(key, pub);
    }
    pub.twin  = id;
    pub.count++;
    pub.t     = w.t;

    // the message travelling from the publisher to its twin
    flight(w, 'sample', { twin: id, from: pub.key, dur: PULSE_FLIGHT });
  }

  // ---- inferred verbs: arcs and markers -----------------------------------

  // One arc.  `delay` starts it later than now, which is how a request
  // and its answer read as one round trip instead of two things crossing.
  function flight(w, kind, opts = {}) {
    w.flights.push({
      kind,
      twinId: opts.twin || null,
      task:   opts.task || null,
      label:  opts.label || null,
      from:   opts.from || null,
      dur:    opts.dur || FLIGHT,
      t0:     w.t + (opts.delay || 0),
    });
    if (w.flights.length > 400) w.flights.shift();
  }

  function marker(w, twinId, label, color) {
    w.markers.push({ twinId, label, color, t0: w.t });
    if (w.markers.length > 80) w.markers.shift();
  }

  function expire(w) {
    armTasks(w);

    w.flights = w.flights.filter(f => w.t - f.t0 < f.dur + 0.1);
    w.markers = w.markers.filter(m => w.t - m.t0 < MARKER_TTL);

    for (const [uid, t] of w.tasks) {
      if (t.tEnd !== null) {
        if (w.t - t.tEnd > FADE && t.due === null) w.tasks.delete(uid);
        continue;
      }
      // A terminal event lost in an SSE reconnect gap would otherwise
      // leave a tile pulsing RUNNING for the rest of the session, holding
      // its slot and its place in the tally.  The trade this makes is
      // deliberate: a task that really does run longer than TASK_TTL
      // stops being drawn.  Its fate is unknown, so it leaves the
      // running count without joining `done` or `failed`.
      if (w.t - t.seen > TASK_TTL) {
        w.counts[t.lane].running = Math.max(0, w.counts[t.lane].running - 1);
        w.tasks.delete(uid);
      }
    }
    // A twin that left `twin_list` lingers: its card is the only record of
    // what it was doing, and a twin that closes at the end of a run used to
    // take that away within two seconds -- long before anyone watching had
    // read it.  The card holds its final state pill, fades over the last of
    // the grace period, and yields its grid slot to live twins meanwhile
    // (see `drawBrokerLane`).  Its tasks stay its own while it is up: it
    // really did submit them, and the card is what says so.
    for (const [id, tw] of w.twins) {
      if (tw.gone !== null && w.t - tw.gone > GONE_LINGER) w.twins.delete(id);
    }
  }

  function num(v) { return typeof v === 'number' && isFinite(v) ? v : null; }

  // =========================================================================
  //  SOURCES -- replay and live, both emitting the same frames
  // =========================================================================

  // A recording.  Frames are handed over when the model clock passes their
  // timestamp, so pause and the speed slider act on the *data*, not on an
  // animation that happens to be drawn from it.
  function ReplaySource(recording, sink) {
    const frames = (recording && recording.frames) || [];
    let i = 0;

    return {
      mode:     'replay',
      broker:   recording.broker || '',
      duration: frames.length ? frames[frames.length - 1].t : 0,
      frames:   frames.length,
      label: recording.recorded
        ? `replay · ${String(recording.recorded).replace('T', ' ')
                                               .replace(/\..*/, '')} UTC`
        : 'replay',
      advance(t) {
        while (i < frames.length && frames[i].t <= t) sink(frames[i++]);
      },
      get done() { return i >= frames.length; },
      rewind() { i = 0; },
      stop() {},
    };
  }

  // One frame of a recording: the envelope, and of the payload only what
  // something here reads.  On a long capture that is most of the bytes,
  // and every dropped field is one nothing could have drawn:
  //
  //   - a DT stream event's payload is a cloudpickled blob only its
  //     subscribers can read, and its `endpoint` is the plugin host's own
  //     participant name.  The *topic* is what draws the pulse (it names
  //     the twin and the dtype), so the topic travels and those two do not.
  //   - a task status carries the task's own return value and exit code;
  //     the tiles are drawn from `uid` and `state` alone.
  //   - a twin's `config` and a session's `idle` are reported by the
  //     service and read by nothing on this canvas.
  //   - a twin's `tasks` is a *ring*: every poll repeats the uids the last
  //     one carried, and the model only ever adds them to a map that
  //     already has them.  A recording therefore keeps each uid once, on
  //     the first poll that showed it -- `seen` is what remembers, and it
  //     turns the biggest field on the wire into one line per task.
  function captureFrame(t, frame, seen) {
    let data = frame.data;

    if (frame.kind === 'snapshot' && data) {
      data = { ...data,
               sessions: (data.sessions || []).map(s => captureSession(s, seen)) };
    } else if (frame.kind === 'event' && data) {
      if (data.plugin === 'dt_stream') {
        data = { plugin: data.plugin, topic: data.topic, data: {} };
      } else if (data.topic === 'task_status' && data.data) {
        data = { ...data, data: { uid: data.data.uid,
                                  state: data.data.state } };
      } else if (data.topic === 'task_status_batch' && data.data) {
        data = { ...data, data: { tasks: (data.data.tasks || []).map(
          task => ({ uid: task.uid, state: task.state })) } };
      }
    }

    return { t: round(t, 3), kind: frame.kind, data };
  }

  function captureSession(session, seen) {
    const { idle, twins, ...rest } = session;
    void idle;

    return { ...rest, twins: (twins || []).map(twin => {
      const { config, ...kept } = twin;
      void config;

      if (Array.isArray(kept.tasks) && seen) {
        kept.tasks = kept.tasks.filter(uid => !seen.has(uid));
        for (const uid of kept.tasks) seen.add(uid);
      }

      return kept;
    }) };
  }

  // The live stack: a 1 Hz `admin/sessions` poll plus the gateway's SSE
  // feed.  Both are turned into the same frames a recording holds, which
  // is what makes `Record` a memcpy rather than a second serializer.
  function LiveSource(opts, sink, onStatus) {
    const broker = (opts.brokerUrl || '').replace(/\/$/, '');
    const dtPath = (opts.dtPath || '/broker/dt').replace(/\/$/, '');
    const url    = path => `${broker}${path}`;

    let timer = null, esTimer = null, es = null, stopped = false;
    let polls = 0, fails = 0, esFails = 0;

    async function auth() {
      // A token mints the cookie the EventSource needs; without one we
      // assume the browser already holds it (the Explorer host does).
      if (!opts.token) return;
      const resp = await fetch(url('/auth'), {
        method: 'POST',
        headers: { authorization: `Bearer ${opts.token}` },
        credentials: 'include',
      });
      if (!resp.ok) throw new Error(`auth failed: HTTP ${resp.status}`);
    }

    async function poll() {
      try {
        const resp = await fetch(url(`${dtPath}/admin/sessions`), {
          credentials: 'include',
          headers: opts.token ? { authorization: `Bearer ${opts.token}` } : {},
          // a poll that outlives its own period is a poll nobody wants
          signal: AbortSignal.timeout(POLL_TIMEOUT * 1000),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const snapshot = await resp.json();

        // A response that lands after this source was replaced describes
        // a world that no longer exists; sinking it would inject a stale
        // snapshot into the new one and infer verbs from the difference.
        if (stopped) return;

        sink({ kind: 'snapshot', data: snapshot });
        polls++;
        fails = 0;
        onStatus(`live · ${broker || 'same origin'} · ${polls} polls`, true);
      } catch (exc) {
        if (stopped) return;
        fails++;
        onStatus(`poll failed (${fails}): ${exc.message}`, false);
      }
    }

    // One poll in flight at a time, the next scheduled from the previous
    // one's completion.  `setInterval` would overlap on a slow broker and
    // deliver snapshots out of order -- which the delta inference reads as
    // twins vanishing and coming straight back, arcs and all.  Chaining
    // also stops the period drifting under a loaded tab.
    function schedule() {
      timer = setTimeout(async () => {
        await poll();
        if (!stopped) schedule();
      }, POLL_INTERVAL * 1000);
    }

    function events() {
      es = new EventSource(url('/events'), { withCredentials: true });

      es.onopen = () => { esFails = 0; };
      es.onmessage = ev => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        if (stopped) return;
        if (msg && msg.topic === 'notification') {
          sink({ kind: 'event', data: msg.data });
        }
      };

      // The browser reconnects an EventSource itself only while it is
      // CONNECTING; a CLOSED one stays closed for good, and a dashboard
      // that has quietly stopped seeing tasks looks like an idle service.
      es.onerror = () => {
        if (stopped) return;
        if (es.readyState !== 2 /* CLOSED */) {
          onStatus('event stream interrupted, reconnecting…', false);
          return;
        }
        const wait = Math.min(SSE_BACKOFF, 2 ** Math.min(esFails++, 5));
        onStatus(`event stream closed, retrying in ${wait}s`, false);
        esTimer = setTimeout(() => { if (!stopped) events(); }, wait * 1000);
      };
    }

    return {
      mode:   'live',
      broker: broker || location.origin,
      advance() {},                  // frames arrive when they arrive
      async start() {
        await auth();
        if (stopped) return;
        await poll();
        if (stopped) return;
        schedule();
        events();
      },
      stop() {
        stopped = true;
        if (timer) clearTimeout(timer);
        if (esTimer) clearTimeout(esTimer);
        if (es) es.close();
        timer = esTimer = es = null;
      },
    };
  }

  // =========================================================================
  //  THE DASHBOARD -- DOM, controls, frame loop
  // =========================================================================

  function newDash(host, opts) {
    injectCss();

    const root  = el('div', 'dtd-root');
    const stage = el('div', 'dtd-stage');
    const cv    = document.createElement('canvas');
    cv.className = 'dtd-canvas';
    stage.appendChild(cv);
    root.appendChild(stage);

    const bar = el('div', 'dtd-controls');
    root.appendChild(bar);
    host.appendChild(root);

    const ctx = cv.getContext('2d');

    let world   = newWorld();
    let source  = null;
    let playing = true;
    let speed   = 1.0;
    let status  = { text: 'no data', ok: false };
    let hover   = null;        // {x, y} in canvas coordinates
    let capture = null;        // {t0, iso, broker, frames} while recording
    // per-card collapse state (`dt:<twinId>`, `agent:<twinId>|<name>`);
    // hits is rebuilt by the renderer each frame so the click handler
    // can hit-test against exactly the clickable header regions.
    // `seenTwins` records ids already inserted into `collapsed` by the
    // default-collapsed rule, so a user's expand click on a freshly-seen
    // twin sticks instead of being re-collapsed on the next frame.
    const collapsed = new Set();
    const seenTwins = new Set();
    let hits = [];
    // what the last frame drew, for `frame()`: the layout and every arc the
    // renderer resolved, so a test (or a console) sees the real geometry
    const probe = { t: 0, L: null, arcs: [] };
    let W = 0, H = 0, dpr = 1;

    const sink = frame => {
      ingest(world, frame);
      if (!capture) return;

      capture.frames.push(captureFrame(world.t - capture.t0, frame,
                                       capture.seen));

      // Bounded, and it has to be: under the orbit data plane every
      // stream message is an event on this feed, so an unattended `rec`
      // on a chatty twin would grow until the tab dies.  Stop at the cap
      // and hand over what was captured rather than losing all of it.
      if (capture.frames.length >= CAPTURE_MAX) {
        toggleRecord(`recording stopped at the ${CAPTURE_MAX}-frame cap`);
      }
    };

    // ---- controls ---------------------------------------------------------

    const $play     = btn('&#10074;&#10074; pause', () => setPlaying(!playing));
    $play.classList.add('dtd-play');
    const $speedLbl = label('speed');
    const $speed    = range(0.25, 8, 0.05, 1);
    const $speedVal = el('span', 'dtd-num', '1.00×');
    const $mode     = el('span', 'dtd-badge', 'IDLE');
    const $rec      = btn('&#9679; rec', () => toggleRecord());
    const $file     = fileInput();
    const $url      = input(opts.brokerUrl || '', 'broker url', 190);
    const $token    = input(opts.token || '', 'token', 120);
    $token.type = 'password';
    const $connect  = btn('connect', connect);

    bar.appendChild($play);
    bar.appendChild($speedLbl);
    bar.appendChild($speed);
    bar.appendChild($speedVal);
    bar.appendChild($mode);
    bar.appendChild(el('span', 'dtd-spacer'));
    if (opts.sample) bar.appendChild(btn('sample', () => play(opts.sample)));
    bar.appendChild(btn('load…', () => $file.click()));
    bar.appendChild($rec);
    bar.appendChild($file);
    if (!opts.compact) {
      bar.appendChild(el('span', 'dtd-spacer'));
      bar.appendChild($url);
      bar.appendChild($token);
      bar.appendChild($connect);
    }

    $speed.oninput = e => {
      speed = parseFloat(e.target.value);
      $speedVal.textContent = speed.toFixed(2) + '×';
    };
    $file.onchange = () => {
      const f = $file.files && $file.files[0];
      if (f) readRecording(f);
      $file.value = '';
    };

    // drag a recording onto the canvas
    stage.addEventListener('dragover', e => {
      e.preventDefault();
      stage.classList.add('dtd-drop');
    });
    stage.addEventListener('dragleave',
                           () => stage.classList.remove('dtd-drop'));
    stage.addEventListener('drop', e => {
      e.preventDefault();
      stage.classList.remove('dtd-drop');
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) readRecording(f);
    });

    function setPlaying(on) {
      playing = on;
      $play.innerHTML = on ? '&#10074;&#10074; pause' : '&#9654; play';
    }

    // Play / pause and the speed slider belong to a *recording*; a live
    // view has nothing to seek and nothing to slow down, so they go away
    // instead of pretending.  Recording, symmetrically, is live-only.
    function setMode(mode) {
      const replay = mode === 'replay';
      for (const node of [$play, $speedLbl, $speed, $speedVal]) {
        node.style.display = replay ? '' : 'none';
      }
      $rec.style.display = mode === 'live' ? '' : 'none';
      $mode.textContent = mode.toUpperCase();
      $mode.className = 'dtd-badge' + (mode === 'live' ? ' dtd-live' : '');
    }

    function setStatus(text, ok) { status = { text, ok }; }

    // ---- sources ----------------------------------------------------------

    function reset() {
      if (source) source.stop();
      if (capture) toggleRecord();
      source = null;
      world = newWorld();
    }

    function play(recording) {
      if (!recording || recording.schema !== SCHEMA) {
        setStatus(`not a ${SCHEMA} recording`, false);
        return;
      }
      reset();
      source = ReplaySource(recording, sink);
      setMode('replay');
      setStatus(`${source.label} · ${source.frames} frames`, true);
      setPlaying(true);
    }

    function connect() {
      reset();
      const live = LiveSource(
        { brokerUrl: $url.value.trim(), token: $token.value.trim(),
          dtPath: opts.dtPath },
        sink, setStatus);
      source = live;
      setMode('live');
      setPlaying(true);
      setStatus('connecting…', true);
      live.start().catch(exc => setStatus(exc.message, false));
    }

    function readRecording(file) {
      const reader = new FileReader();
      reader.onload = () => {
        try {
          play(JSON.parse(reader.result));
        } catch (exc) {
          setStatus(`cannot read ${file.name}: ${exc.message}`, false);
        }
      };
      reader.readAsText(file);
    }

    // ---- recording --------------------------------------------------------

    // `note` is set when the recording stopped itself rather than being
    // stopped; it replaces the confirmation with the reason.
    function toggleRecord(note) {
      if (capture) {
        const rec = {
          schema:   SCHEMA,
          recorded: capture.iso,
          broker:   capture.broker,
          duration: capture.frames.length
            ? capture.frames[capture.frames.length - 1].t : 0,
          frames:   capture.frames,
        };
        download(`dt-recording-${rec.recorded.replace(/[:.]/g, '-')}.json`,
                 JSON.stringify(rec));
        capture = null;
        $rec.classList.remove('dtd-active');
        $rec.innerHTML = '&#9679; rec';
        setStatus(note || `recorded ${rec.frames.length} frames`, !note);
        return;
      }

      capture = {
        t0: world.t, iso: new Date().toISOString(),
        broker: (source && source.broker) || '', frames: [],
        seen: new Set(),      // task uids already written (see `captureFrame`)
      };
      $rec.classList.add('dtd-active');
      $rec.innerHTML = '&#9632; stop rec';
    }

    // ---- canvas sizing: adaptive, devicePixelRatio-aware -----------------

    function resize() {
      const r = stage.getBoundingClientRect();
      dpr = window.devicePixelRatio || 1;
      W = Math.max(360, Math.round(r.width));
      H = Math.max(240, Math.round(r.height));
      cv.width  = Math.round(W * dpr);
      cv.height = Math.round(H * dpr);
      cv.style.width  = W + 'px';
      cv.style.height = H + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    const ro = new ResizeObserver(resize);
    ro.observe(stage);

    // devicePixelRatio changes without a resize when the window moves to a
    // display of another density, and a stale one draws the whole canvas
    // blurry.  A resolution media query is the only event for it, and it
    // has to be re-armed against the new ratio each time it fires.
    let dprQuery = null;

    function watchDpr() {
      if (!window.matchMedia) return;
      if (dprQuery) dprQuery.removeEventListener('change', onDpr);
      dprQuery = window.matchMedia(`(resolution: ${dpr}dppx)`);
      dprQuery.addEventListener('change', onDpr);
    }

    function onDpr() {
      resize();
      watchDpr();
    }

    resize();
    watchDpr();

    cv.addEventListener('mousemove', e => {
      const r = cv.getBoundingClientRect();
      hover = { x: e.clientX - r.left, y: e.clientY - r.top };
      // cheap cursor cue: show the pointer when over a clickable header
      let overHit = false;
      for (const h of hits) {
        if (hover.x >= h.x && hover.x <= h.x + h.w
            && hover.y >= h.y && hover.y <= h.y + h.h) { overHit = true; break; }
      }
      cv.style.cursor = overHit ? 'pointer' : '';
    });
    cv.addEventListener('mouseleave', () => { hover = null; });
    cv.addEventListener('click', e => {
      const r = cv.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      for (const h of hits) {
        if (x >= h.x && x <= h.x + h.w && y >= h.y && y <= h.y + h.h) {
          if (collapsed.has(h.key)) collapsed.delete(h.key);
          else collapsed.add(h.key);
          return;
        }
      }
    });

    // ---- frame loop -------------------------------------------------------

    let last = performance.now();
    let seen = false;          // has this dashboard ever been in the document?
    let raf  = requestAnimationFrame(frame);

    function frame() {
      // The ORBIT Explorer drops a page's node on disconnect without
      // telling the module that drew it, and nothing else ever calls
      // `destroy()` there.  Without this, every connect/disconnect cycle
      // would leave another poll, EventSource and RAF loop running against
      // a canvas nobody can see.
      if (root.isConnected) seen = true;
      else if (seen) { destroy(); return; }

      const now = performance.now();
      const dt  = Math.min(0.25, (now - last) / 1000);
      last = now;

      if (source && (playing || source.mode === 'live')) {
        world.t += dt * (source.mode === 'replay' ? speed : 1);
        source.advance(world.t);
        expire(world);

        // a finished recording loops, after a beat on the last frame
        if (source.mode === 'replay' && source.done
            && world.t > source.duration + 1.5) {
          source.rewind();
          world = newWorld();
        }
      }

      probe.arcs = [];
      hits = [];
      render(ctx, W, H, world,
             { status, hover, probe, collapsed, seenTwins, hits });
      raf = requestAnimationFrame(frame);
    }

    function destroy() {
      cancelAnimationFrame(raf);
      ro.disconnect();
      if (dprQuery) dprQuery.removeEventListener('change', onDpr);
      dprQuery = null;
      reset();
      root.remove();
    }

    // ---- start ------------------------------------------------------------

    setMode('idle');
    if (opts.live) connect();
    else if (opts.sample) play(opts.sample);
    else setStatus('load a recording, or connect to a broker', false);

    return {
      world: () => world,
      frame: () => probe,
      play,
      connect,
      setStatus,
      destroy,
    };
  }

  // =========================================================================
  //  RENDER
  // =========================================================================

  function render(ctx, W, H, w, ui) {
    const L = layout(W, H);

    // the probe carries this frame's geometry back out to `frame()`: a test
    // then reads the arcs the renderer resolved, on the code path a browser
    // runs, instead of re-deriving them and being wrong in its own way
    if (ui.probe) { ui.probe.L = L; ui.probe.t = w.t; }

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);

    drawHeader(ctx, L, w, ui);
    drawSensorLane(ctx, L, w);
    drawBrokerLane(ctx, L, w, ui);
    drawHpcLanes(ctx, L, w);
    drawFlights(ctx, L, w, ui);
    drawTooltip(ctx, L, w, ui);
  }

  // ---- layout: everything derived from the container's size --------------

  function layout(W, H) {
    const S  = Math.max(0.7, Math.min(1.35, W / 1280));
    const M  = Math.round(13 * S);
    const G  = Math.round(11 * S);
    const hd = Math.round(38 * S);

    const top    = hd + Math.round(4 * S);
    const height = H - top - M;
    const inner  = W - 2 * M - 2 * G;

    const cw = Math.max(Math.round(96 * S), Math.round(inner * 0.11));
    const hw = Math.max(Math.round(230 * S), Math.round(inner * 0.33));
    const bw = inner - cw - hw;

    // The left column is now the sensors lane, full height.  The client
    // frame is gone -- but the create / destroy / call arcs still need an
    // origin, and `client` here is that virtual anchor: a 1x1 rect on the
    // broker's left edge, off-canvas from anything drawn.  Arcs then read
    // as coming in from outside the visible layout, which is where the
    // client is now (see the note in `flightPath`).
    const sensors = { x: M, y: top, w: cw, h: height };
    const broker  = { x: M + cw + G,          y: top, w: bw, h: height };
    const hpc     = { x: M + cw + G + bw + G, y: top, w: hw, h: height };
    const client  = { x: broker.x - 1, y: broker.y + Math.round(20 * S),
                      w: 1, h: 1 };

    // the HPC super-frame holds the two endpoint role lanes, stacked
    const head = Math.round(26 * S);
    const subH = Math.floor((hpc.h - head - G - Math.round(7 * S)) / 2);
    const inference = { x: hpc.x + Math.round(8 * S), y: hpc.y + head,
                        w: hpc.w - Math.round(16 * S), h: subH };
    const learning = { x: inference.x, y: inference.y + subH + G,
                       w: inference.w, h: subH };

    return { S, M, G, hd, W, H, client, sensors, broker, hpc,
             inference, learning };
  }

  // ---- primitives (the reference's idioms) -------------------------------

  function rr(ctx, x, y, wd, ht, r) {
    r = Math.max(0, Math.min(r, wd / 2, ht / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + wd, y,      x + wd, y + ht, r);
    ctx.arcTo(x + wd, y + ht, x,      y + ht, r);
    ctx.arcTo(x,      y + ht, x,      y,      r);
    ctx.arcTo(x,      y,      x + wd, y,      r);
    ctx.closePath();
  }

  // Letter-spaced ALL CAPS -- the slide deck's section-header idiom.
  function spaced(ctx, text, x, y, gap) {
    let cur = x;
    for (const ch of text) {
      ctx.fillText(ch, cur, y);
      cur += ctx.measureText(ch).width + gap;
    }
    return cur - x - gap;
  }

  function spacedWidth(ctx, text, gap) {
    let wd = -gap;
    for (const ch of text) wd += ctx.measureText(ch).width + gap;
    return wd;
  }

  function panel(ctx, r, border, text, textColor, S, fill) {
    ctx.fillStyle = fill || C.panel;
    rr(ctx, r.x, r.y, r.w, r.h, 8 * S);
    ctx.fill();
    ctx.strokeStyle = border;
    ctx.lineWidth = 1.5;
    rr(ctx, r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1, 8 * S);
    ctx.stroke();

    if (text) {
      ctx.fillStyle = textColor || border;
      ctx.font = `600 ${Math.round(10.5 * S)}px ${FONT}`;
      ctx.textBaseline = 'top';
      ctx.textAlign = 'left';
      spaced(ctx, text.toUpperCase(), r.x + 12 * S, r.y + 10 * S, 0.8);
    }
  }

  function pillWidth(ctx, text, S) {
    ctx.font = `600 ${Math.round(9.5 * S)}px ${FONT}`;
    return spacedWidth(ctx, text.toUpperCase(), 0.6) + 12 * S;
  }

  function pill(ctx, x, y, text, color, S) {
    const pw = pillWidth(ctx, text, S);
    const ph = 14 * S;

    ctx.globalAlpha *= 0.16;
    ctx.fillStyle = color;
    rr(ctx, x, y, pw, ph, 3 * S);
    ctx.fill();
    ctx.globalAlpha /= 0.16;

    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    rr(ctx, x + 0.5, y + 0.5, pw - 1, ph - 1, 3 * S);
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    spaced(ctx, text.toUpperCase(), x + 6 * S, y + ph / 2 + 0.5, 0.6);

    return pw;
  }

  function clip(ctx, text, maxW) {
    text = String(text);
    if (ctx.measureText(text).width <= maxW) return text;
    let out = text;
    while (out.length > 1 && ctx.measureText(out + '…').width > maxW) {
      out = out.slice(0, -1);
    }
    return out + '…';
  }

  // Ids are uuids (twins) or `session.<hex>` (sessions): the first eight
  // characters identify a twin, but for a session they are the word
  // "session", so a prefix like that is dropped first.
  function short(id) {
    return String(id).replace(/^[a-z_]+\./, '').slice(0, 8);
  }

  function round(v, n) { const f = 10 ** n; return Math.round(v * f) / f; }

  function fmt(v) {
    if (typeof v !== 'number' || !isFinite(v)) return '-';
    const a = Math.abs(v);
    if (a === 0) return '0';
    if (a >= 1000 || a < 0.001) return v.toExponential(1);
    return v.toFixed(a < 1 ? 3 : 2);
  }

  function humanAge(sec) {
    if (sec < 90) return `${sec.toFixed(0)}s`;
    if (sec < 5400) return `${(sec / 60).toFixed(0)}m`;
    if (sec < 172800) return `${(sec / 3600).toFixed(1)}h`;
    return `${(sec / 86400).toFixed(1)}d`;
  }

  // Placeholder card content: the wire does not carry per-twin
  // components, utility-task counts or per-investigator RMSE yet, so all
  // three are synthesised here.  The agent roster is fixed (every twin
  // runs the same two, each carrying an ANN and an RNN investigator),
  // and the utility counts / RMSE traces are deterministic from a seed
  // so they stay stable across frames and replays.  Swap `fakeAgents` /
  // `fakeUtility` / `fakeSpark` the day the service starts serialising
  // `runtime.components`.
  const FAKE_AGENTS = [
    { name: 'Gravity Estimator',  inD: 'SENSOR', outD: 'GRAVITY'  },
    { name: 'Velocity Estimator', inD: 'SENSOR', outD: 'VELOCITY' },
  ];

  const FAKE_INVESTIGATORS = ['ANN', 'RNN'];

  // A per-investigator model name that ticks up once a second, offset by
  // the seed so investigators don't all read the same version.
  function fakeModelName(seed, tick) {
    const start = 1 + (Math.abs(seed) % 30);
    return `model-v${start + tick}`;
  }

  function fakeAgents() { return FAKE_AGENTS; }

  function fnv1a(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h;
  }

  function fakeUtility(id) {
    const h = fnv1a(id);
    const total   = 2 + (Math.abs(h) % 5);                          // 2-6
    const persist = 1 + (Math.abs(h >>> 5) % Math.min(3, total));   // 1..min(3,total)
    return { total, persist };
  }

  // A per-investigator RMSE trace, sampled to the model clock so it
  // slides as `w.t` advances.  Starts high, decays with mild oscillation
  // -- looks like a learner converging.  Nothing here reads real state.
  function fakeSpark(seed, t) {
    const N = 28, step = 0.5;
    const out = [];
    const t0 = t - N * step;
    for (let i = 0; i < N; i++) {
      const tt = t0 + i * step;
      const decay = Math.exp(-Math.max(0, tt) / 40);
      const noise = Math.sin(tt * 0.9 + seed * 1.31) * 0.08
                  + Math.cos(tt * 0.31 + seed * 0.71) * 0.05;
      out.push(Math.max(0.01, 0.10 + 0.9 * decay + noise * decay));
    }
    return out;
  }

  // ---- header ------------------------------------------------------------

  function drawHeader(ctx, L, w, ui) {
    const S = L.S, cy = Math.round(L.hd / 2) + 2;

    ctx.fillStyle = C.cyan;
    ctx.beginPath();
    ctx.arc(L.M + 4 * S, cy, 3.6 * S, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = C.text;
    ctx.font = `600 ${Math.round(15 * S)}px ${FONT}`;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    const wd = spaced(ctx, 'DIGITAL TWIN SERVICE', L.M + 14 * S, cy, 1.0);

    // The data plane's backend, stated up front: it is the difference
    // between open ZMQ ports and the token-authenticated star (M3 / R7).
    let x = L.M + 14 * S + wd + 14 * S;
    if (w.backend) {
      const color = w.backend === 'orbit' ? C.green : C.amber;
      x += pill(ctx, x, cy - 7 * S, `stream ${w.backend}`, color, S) + 6 * S;
    }
    if (w.stream && w.backend === 'zmq' && w.stream.addresses
        && w.stream.alive === false) {
      x += pill(ctx, x, cy - 7 * S, 'stream broker down', C.red, S) + 6 * S;
    }

    // Which build is drawing this.  A browser holds a file:// script in its
    // cache well past the edit that changed it, and the copy the broker
    // serves is only as new as the last `pip install .` -- a stale dashboard
    // beside a fresh recording otherwise looks exactly like a bug in the
    // dashboard.  If this is not the version in the source tree, that is
    // the first thing to fix.
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
    ctx.textBaseline = 'middle';
    ctx.textAlign = 'left';
    ctx.fillText(`v${VERSION}`, x, cy);

    // Live twins, not cards: a closed twin's card lingers as a memento
    // (see `expire`) and counting it here would contradict the client lane,
    // which reports what the last `twin_list` actually held.
    let live = 0;
    for (const tw of w.twins.values()) if (tw.gone === null) live++;

    ctx.textAlign = 'right';
    ctx.font = `400 ${Math.round(10.5 * S)}px ${FONT_MONO}`;
    ctx.fillStyle = ui.status.ok ? C.text_dim : C.amber;
    ctx.fillText(clip(ctx,
      `${ui.status.text}   |   ${live} twins · ${w.tasks.size} tasks`
      + `   |   t = ${w.t.toFixed(1)} s`, L.W * 0.55),
      L.W - L.M, cy);
  }

  // ---- SENSORS lane: the twins' own publishers, as observed ------------
  //
  // Every entry here was seen on the data plane: a `dt_stream` topic names
  // the twin and the dtype, and only a twin's persistent components ever
  // publish.  Nothing is declared and nothing is guessed.
  //
  // The lane sits outside the broker frame because that is where a reader
  // looks for where data comes *from* -- but in v1 these components run
  // inside the plugin host, on its event loop, which the sub-label says.
  function drawSensorLane(ctx, L, w) {
    const S = L.S, r = L.sensors;
    if (r.h < 46 * S) return;

    panel(ctx, r, C.frame_border, 'Channels', C.frame_label, S);

    const pubs = [...w.publishers.values()]
      .sort((a, b) => a.key < b.key ? -1 : 1);

    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    ctx.font = `400 ${Math.round(8 * S)}px ${FONT}`;
    ctx.fillStyle = C.text_dim;
    ctx.fillText(clip(ctx, 'visible to broker', r.w * 0.6),
                 r.x + r.w - 9 * S, r.y + 12 * S);

    if (!pubs.length) {
      placeholder(ctx, r, 'no stream traffic seen', S);
      return;
    }

    const head = Math.round(26 * S);
    const pad  = Math.round(8 * S);
    const rowH = Math.round(20 * S);
    const rows = Math.max(1, Math.floor((r.h - head - pad) / rowH));

    // A narrow lane (the Explorer's) collapses to one row of dtype tiles:
    // which twin publishes what is worth less than the lane staying legible.
    const collapse = rows < 2 || r.h < 74 * S;

    if (collapse) {
      const tile = Math.max(6, Math.round(10 * S));
      const gap  = Math.max(2, Math.round(4 * S));
      pubs.forEach((pub, i) => {
        const x = r.x + pad + i * (tile + gap);
        if (x + tile > r.x + r.w - pad) return;
        pub._rect = { x, y: r.y + head, w: tile, h: tile };
        drawSensorTile(ctx, pub._rect, pub, w, S);
      });
      return;
    }

    pubs.forEach((pub, i) => {
      if (i >= rows) return;
      const y = r.y + head + i * rowH;
      const box = { x: r.x + pad, y, w: r.w - 2 * pad, h: rowH - 4 * S };
      pub._rect = box;

      drawSensorTile(ctx, { x: box.x, y: box.y + 2 * S,
                            w: Math.round(9 * S), h: Math.round(9 * S) },
                     pub, w, S);

      const tx = box.x + Math.round(15 * S);
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';
      ctx.fillStyle = C.text_label;
      ctx.font = `600 ${Math.round(9.5 * S)}px ${FONT}`;
      ctx.fillText(clip(ctx, pub.dtype, box.w * 0.5), tx, box.y + 1 * S);

      ctx.textAlign = 'right';
      ctx.fillStyle = C.text_dim;
      ctx.font = `400 ${Math.round(8.5 * S)}px ${FONT_MONO}`;
      ctx.fillText(`${pub.count}`, box.x + box.w, box.y + 1 * S);
    });

    if (pubs.length > rows) {
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillStyle = C.text_dim;
      ctx.font = `400 ${Math.round(9 * S)}px ${FONT}`;
      ctx.fillText(`+${pubs.length - rows} more`, r.x + r.w - pad,
                   r.y + r.h - 5 * S);
    }
  }

  function drawSensorTile(ctx, box, pub, w, S) {
    const k = Math.max(0, 1 - (w.t - pub.t) / (PULSE_TTL * 1.4));

    ctx.save();
    if (k > 0) {
      ctx.shadowBlur = 10 * k * S;
      ctx.shadowColor = C.green;
    }
    ctx.globalAlpha = 0.35 + 0.65 * k;
    ctx.fillStyle = C.green;
    rr(ctx, box.x, box.y, box.w, box.h, 2);
    ctx.fill();
    ctx.restore();
  }

  function placeholder(ctx, r, text, S) {
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(11 * S)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, r.x + r.w / 2, r.y + r.h / 2);
  }

  // ---- BROKER lane: the twin cards are the centrepiece -------------------

  // The demo runs two digital twins.  The bundled sample recording holds
  // more; anything past the cap gets `+N more` at the bottom of the lane.
  const DEMO_TWIN_CAP = 2;

  function drawBrokerLane(ctx, L, w, ui) {
    const S = L.S, r = L.broker;
    panel(ctx, r, C.cyan_dim, 'Digital Twins in Service on Broker',
          C.frame_label, S);

    // Birth order, except that a twin which has gone yields its slot: its
    // card is a memento, and a live twin pushed behind `+N more` by one is
    // a worse trade than a memento moving.
    const allTwins = [...w.twins.values()].sort((a, b) =>
      (a.gone === null ? 0 : 1) - (b.gone === null ? 0 : 1) || a.born - b.born);
    if (!allTwins.length) {
      placeholder(ctx, r, 'no twins', S);
      return;
    }
    const twins = allTwins.slice(0, DEMO_TWIN_CAP);

    // Newly-observed twins start collapsed.  `seenTwins` gates this so
    // a user's expand click on a fresh twin isn't undone next frame.
    for (const tw of twins) {
      if (!ui.seenTwins.has(tw.id)) {
        ui.seenTwins.add(tw.id);
        ui.collapsed.add(`dt:${tw.id}`);
      }
    }

    const head = Math.round(28 * S);
    const pad  = Math.round(9 * S);
    const gap  = Math.round(8 * S);

    // One column, variable height: a collapsed card is a slim strip, an
    // expanded card is as tall as the sum of its (possibly-collapsed)
    // agents.  Cards past what fits get `+N more`.
    const cardW = r.w - 2 * pad;
    const top    = r.y + head;
    const bottom = r.y + r.h - pad;

    let cursor = top;
    let shown  = 0;
    for (const tw of twins) {
      const cardH = twinCardHeight(tw, ui, S);
      if (cursor + cardH > bottom) break;
      const box = { x: r.x + pad, y: cursor, w: cardW, h: cardH };
      tw._rect = box;
      drawTwinCard(ctx, box, tw, w, S, ui);
      cursor += cardH + gap;
      shown++;
    }
    for (let i = shown; i < allTwins.length; i++) allTwins[i]._rect = null;

    const hidden = allTwins.length - shown;
    if (hidden > 0) {
      ctx.fillStyle = C.text_dim;
      ctx.font = `400 ${Math.round(10 * S)}px ${FONT}`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText(`+${hidden} more`,
                   r.x + r.w - pad, r.y + r.h - 4 * S);
    }
  }

  // Sizing that both the layout and `drawTwinCard` agree on.  Kept as
  // one function so a change to any padding is a single edit.
  const DT_HEAD_H   = 20;   // title row (font 12) baseline
  const DT_UTIL_H   = 16;   // utility line (font 9.5)
  const DT_TOP_PAD  = 7;
  const DT_BOT_PAD  = 8;
  const DT_AGENT_GAP = 6;
  const AGENT_COLLAPSED_H = 42;
  const AGENT_EXPANDED_H  = 140;

  function agentHeight(twinId, agentName, ui, S) {
    const key = `agent:${twinId}|${agentName}`;
    const h   = ui.collapsed.has(key) ? AGENT_COLLAPSED_H : AGENT_EXPANDED_H;
    return Math.round(h * S);
  }

  function twinCardHeight(tw, ui, S) {
    const headBlock = Math.round((DT_TOP_PAD + DT_HEAD_H + DT_UTIL_H) * S);
    if (ui.collapsed.has(`dt:${tw.id}`)) {
      return headBlock + Math.round(DT_BOT_PAD * S);
    }
    const agents = fakeAgents();
    let h = headBlock + Math.round(DT_AGENT_GAP * S);
    agents.forEach((a, i) => {
      h += agentHeight(tw.id, a.name, ui, S);
      if (i < agents.length - 1) h += Math.round(DT_AGENT_GAP * S);
    });
    return h + Math.round(DT_BOT_PAD * S);
  }

  function drawTwinCard(ctx, box, tw, w, S, ui) {
    const state = tw.state || 'initializing';
    const closing = tw.gone !== null;
    const dtKey = `dt:${tw.id}`;
    const dtCollapsed = ui.collapsed.has(dtKey);

    // A card that has gone stays up for the whole grace period at a dimmed
    // but readable strength, then fades over the last of it; what it keeps
    // is the last thing the service said about the twin.
    let alpha = 1;
    if (closing) {
      const left = GONE_LINGER - (w.t - tw.gone);
      alpha = 0.7 * Math.max(0, Math.min(1, left / GONE_FADE));
    } else if (w.t - tw.fresh < 0.4) alpha = (w.t - tw.fresh) / 0.4;
    ctx.globalAlpha = alpha;

    // `initializing` pulses: the twin is busy with something slow (engine
    // build + stream connect, up to minutes) and has no runtime yet
    const border = STATE_COLOR[state] || C.grey;
    if (state === 'initializing') {
      ctx.globalAlpha = alpha
        * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin((w.t - tw.born) * 3.2)));
    }
    panel(ctx, box, border, null, null, S, C.panel_deep);
    ctx.globalAlpha = alpha;

    // a stream pulse: an expanding ring on the twin that published
    if (tw.pulse && w.t - tw.pulse.t < PULSE_TTL) {
      const k = 1 - (w.t - tw.pulse.t) / PULSE_TTL;
      ctx.save();
      ctx.globalAlpha = alpha * k * 0.85;
      ctx.strokeStyle = C.green;
      ctx.lineWidth = 1.5;
      const g = 3 * S * (1 - k);
      rr(ctx, box.x - g, box.y - g, box.w + 2 * g, box.h + 2 * g, 9 * S);
      ctx.stroke();
      ctx.restore();
    }

    const px = box.x + 9 * S;
    const maxW = box.w - 18 * S;
    let y = box.y + Math.round(DT_TOP_PAD * S);

    // Title row + clickable header (chevron + "DT: <hash>").  The whole
    // title strip toggles collapse.
    const chevron = dtCollapsed ? '▸' : '▾';   // ▸ ▾
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = C.text;
    ctx.font = `600 ${Math.round(12 * S)}px ${FONT_MONO}`;
    ctx.fillText(clip(ctx, `${chevron} DT: ${short(tw.id)}`,
                      maxW - pillWidth(ctx, state, S) - 6 * S),
                 px, y);

    pill(ctx, box.x + box.w - 9 * S - pillWidth(ctx, state, S), y - 1,
         state, STATE_TEXT[state] || C.text_dim, S);

    // Utility-task count line -- kept visible even when the DT card is
    // collapsed, so a rolled-up card still reports what it holds.
    // Placeholder counts (`fakeUtility`) until the service reports them.
    const utilY = y + Math.round(DT_HEAD_H * S);
    const util  = fakeUtility(tw.id);
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(9.5 * S)}px ${FONT}`;
    ctx.fillText(clip(ctx, `Utility Tasks ${util.total}`
                      + ` (Persist: ${util.persist})`, maxW),
                 px, utilY);

    // Register the clickable region: full title + utility area, so a
    // click anywhere on the visible-when-collapsed portion toggles.
    ui.hits.push({
      key: dtKey,
      x: box.x, y: box.y,
      w: box.w, h: Math.round((DT_TOP_PAD + DT_HEAD_H + DT_UTIL_H) * S),
    });

    y = utilY + Math.round(DT_UTIL_H * S);

    if (!dtCollapsed) {
      if (state === 'failed' && tw.last_error) {
        ctx.fillStyle = C.red;
        ctx.font = `400 ${Math.round(9 * S)}px ${FONT}`;
        ctx.fillText(clip(ctx, tw.last_error, maxW), px, y);
        y += 13 * S;
      }

      // Agent blocks.  Placeholder data (`fakeAgents`) until the service
      // starts serialising `runtime.components`; swap the source here.
      const rowGap = Math.round(DT_AGENT_GAP * S);
      const rowPad = Math.round(4 * S);
      const rowX   = px + rowPad;
      const rowW   = maxW - 2 * rowPad;
      y += rowGap;
      const bottom = box.y + box.h - Math.round(DT_BOT_PAD * S)
                   - (closing ? 10 * S : 0);
      const agents = fakeAgents();
      agents.forEach((a, i) => {
        const rowH = agentHeight(tw.id, a.name, ui, S);
        if (y + rowH > bottom + 1) return;
        drawAgentRow(ctx, rowX, y, rowW, rowH, a, tw.id, w, S, ui);
        y += rowH;
        if (i < agents.length - 1) y += rowGap;
      });
    }

    // A card that has gone says so for as long as it is up: the `closed`
    // marker below outlives its own TTL by a beat only, and the state pill
    // still reads whatever the twin was doing when it left the listing.
    if (closing) {
      ctx.fillStyle = C.grey;
      ctx.font = `600 ${Math.round(8.5 * S)}px ${FONT}`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText('▸ closed', box.x + box.w - 8 * S, box.y + box.h - 6 * S);
      ctx.globalAlpha = 1;
      return;
    }

    // the newest inferred verb / transition, bottom-right of the card
    const marks = w.markers.filter(m => m.twinId === tw.id);
    if (marks.length) {
      const m = marks[marks.length - 1];
      ctx.globalAlpha = alpha
        * Math.max(0, Math.min(1, 2 * (1 - (w.t - m.t0) / MARKER_TTL)));
      ctx.fillStyle = m.color;
      ctx.font = `600 ${Math.round(8.5 * S)}px ${FONT}`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText(`▸ ${m.label}`, box.x + box.w - 8 * S,
                   box.y + box.h - 6 * S);
    }

    ctx.globalAlpha = 1;
  }

  // One agent block inside a twin card.  Structure, top to bottom:
  //   NAME (bold)                                          model: <model>
  //   IN <inD>  →  OUT <outD>
  //     ANN [bold]   rmse 0.14   [micro sparkline]
  //     RNN [bold]   rmse 0.11   [micro sparkline]
  // Everything shown here is placeholder data until the service starts
  // serialising `runtime.components`.
  const INV_COLOR = { ANN: C.cyan, RNN: C.violet };

  function drawAgentRow(ctx, x, y, wd, ht, agent, twinId, w, S, ui) {
    const agentKey = `agent:${twinId}|${agent.name}`;
    const agentCollapsed = ui.collapsed.has(agentKey);

    ctx.fillStyle = C.panel_deep;
    rr(ctx, x, y, wd, ht, 4 * S);
    ctx.fill();
    ctx.strokeStyle = C.frame_border;
    ctx.lineWidth = 1;
    rr(ctx, x + 0.5, y + 0.5, wd - 1, ht - 1, 4 * S);
    ctx.stroke();

    const padX = Math.round(10 * S);
    const lx = x + padX;
    const rx = x + wd - padX;
    let ry = y + Math.round(7 * S);

    // Selected investigator (stable per agent) and its current model
    // name, computed first so the agent's name knows the room left over.
    const tick = Math.floor(w.t);
    const selIdx = Math.abs(fnv1a(`sel|${twinId}|${agent.name}`))
                 % FAKE_INVESTIGATORS.length;
    const selInv = FAKE_INVESTIGATORS[selIdx];
    const selModel = fakeModelName(fnv1a(`${twinId}|${agent.name}|${selInv}`),
                                   tick);
    const selText = `Selected: ${selInv}. Model: ${selModel}`;

    ctx.textBaseline = 'top';
    ctx.textAlign = 'right';
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
    ctx.fillText(clip(ctx, selText, wd * 0.6), rx, ry + 1 * S);
    const selW = Math.min(ctx.measureText(selText).width, wd * 0.6);

    // Chevron sits on the agent name so the whole header row reads as
    // clickable.
    const chev = agentCollapsed ? '▸' : '▾';
    ctx.textAlign = 'left';
    ctx.fillStyle = C.text;
    ctx.font = `600 ${Math.round(11 * S)}px ${FONT}`;
    ctx.fillText(clip(ctx, `${chev} Agent: ${agent.name}`,
                      wd - 2 * padX - selW - Math.round(10 * S)),
                 lx, ry);
    ry += 15 * S;

    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
    ctx.fillText(clip(ctx, `IN ${agent.inD}  →  OUT ${agent.outD}`,
                      wd - 2 * padX),
                 lx, ry);
    ry += 14 * S;

    // Click region covers the header (name + selection + IN/OUT), which
    // is exactly what remains when the agent is collapsed.
    ui.hits.push({
      key: agentKey,
      x, y,
      w: wd, h: Math.round(AGENT_COLLAPSED_H * S),
    });

    if (agentCollapsed) return;

    // Investigator cards, each with its own graph.  The trace and model
    // name are both quantised to the model clock at 1 Hz -- the graph
    // shifts and the version ticks once a second, not every frame.
    const indent = Math.round(14 * S);
    const invH   = Math.round(46 * S);
    const invGap = Math.round(4 * S);
    const invX   = lx + indent;
    const invW   = wd - 2 * padX - indent;
    for (const invName of FAKE_INVESTIGATORS) {
      if (ry + invH > y + ht - Math.round(4 * S)) break;
      const seed  = fnv1a(`${twinId}|${agent.name}|${invName}`);
      const hist  = fakeSpark(seed, tick);
      const model = fakeModelName(seed, tick);
      drawInvestigatorCard(ctx, invX, ry, invW, invH, invName, model, hist,
                           INV_COLOR[invName] || C.text_dim, S);
      ry += invH + invGap;
    }
  }

  // Investigator card: bordered in the investigator's own colour so ANN
  // and RNN read as siblings under the agent.  Three rows inside: title
  // + rmse, model name, then the graph.
  function drawInvestigatorCard(ctx, x, y, wd, ht, name, model, hist, color, S) {
    ctx.save();
    ctx.globalAlpha *= 0.55;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    rr(ctx, x + 0.5, y + 0.5, wd - 1, ht - 1, 3 * S);
    ctx.stroke();
    ctx.restore();

    const padX = Math.round(7 * S);
    const lx = x + padX;
    const rx = x + wd - padX;
    let ry = y + Math.round(4 * S);

    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = C.text;
    ctx.font = `700 ${Math.round(9.5 * S)}px ${FONT}`;
    ctx.fillText(`Inv: ${name}`, lx, ry);

    // model on the title row, right-aligned
    ctx.textAlign = 'right';
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(8.5 * S)}px ${FONT_MONO}`;
    ctx.fillText(clip(ctx, `Model: ${model}`, wd * 0.6), rx, ry + 1 * S);
    ry += 13 * S;

    // rmse on its own line beneath
    const cur = hist[hist.length - 1];
    ctx.textAlign = 'left';
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(8.5 * S)}px ${FONT_MONO}`;
    ctx.fillText(`rmse ${cur.toFixed(3)}`, lx, ry);
    ry += 11 * S;

    const graphH = Math.max(1, y + ht - ry - Math.round(3 * S));
    drawMicroSpark(ctx, lx, ry, wd - 2 * padX, graphH, hist, color);
  }

  // Auto-ranged micro sparkline: the whole trace uses the visible min /
  // max, so a slow decay still shows a shape rather than flattening.
  function drawMicroSpark(ctx, x, y, wd, ht, hist, color) {
    if (hist.length < 2) return;

    let lo = Infinity, hi = -Infinity;
    for (const v of hist) { if (v < lo) lo = v; if (v > hi) hi = v; }
    const span = Math.max(hi - lo, 1e-6);

    ctx.save();
    ctx.strokeStyle = color;
    ctx.globalAlpha *= 0.9;
    ctx.lineWidth = 1.15;
    ctx.beginPath();
    const step = wd / (hist.length - 1);
    hist.forEach((v, i) => {
      const py = y + ht - ((v - lo) / span) * ht;
      if (i === 0) ctx.moveTo(x, py);
      else ctx.lineTo(x + i * step, py);
    });
    ctx.stroke();
    ctx.restore();
  }

  // ---- HPC lanes: one per endpoint role ----------------------------------

  // Task-manager graph: seconds on the x-axis (rightmost point is `now`
  // snapped to the previous half-second, so the graph only shifts once
  // every 0.5s and the buckets sit on a stable time grid), pool's
  // running-task count on the y-axis.  Data comes from `recordPoolEvent`,
  // called whenever the pool's running count actually changes; each
  // `POOL_STEP`-second bucket plots the *max* concurrent count seen
  // during that interval, so a spike lasting less than a bucket is
  // preserved as that bucket's height rather than lost between samples.
  const POOL_WINDOW      = 60;     // seconds shown on the x-axis
  const POOL_STEP        = 0.5;    // bucket width, and the graph's tick
  const POOL_TABLE_ROWS  = 5;

  function drawHpcLanes(ctx, L, w) {
    const S = L.S;
    panel(ctx, L.hpc, C.frame_border, 'Endpoint Pools', C.frame_label, S,
          C.panel_deep);

    // Two pool cards, one per role.  Colour keeps them apart at a glance:
    // inference = cyan, learning = amber -- the same convention already
    // used for task-result arcs on the broker lane.  A pool card also
    // lists every endpoint any session put in that role, because the role
    // is a per-session answer and two sessions need not agree.
    drawEndpointLane(ctx, L.inference, 'Pool: inference',
                     w.endpoints.inference.join(', '), 'inference',
                     w, S, C.cyan_dim, null);
    drawEndpointLane(ctx, L.learning, 'Pool: learning',
                     w.endpoints.learning.join(', '), 'learning', w, S,
                     C.amber_dim,
                     w.endpoints.alias ? 'aliases inference' : null);
  }

  // Tile geometry, shared by the renderer and the spawn arcs so a task
  // lands exactly where its tile will be.
  function laneGeom(r, S) {
    const head = Math.round(24 * S);
    const pad  = Math.round(9 * S);
    const tile = Math.max(6, Math.round(11 * S));
    const gap  = Math.max(2, Math.round(3 * S));
    const cols = Math.max(1, Math.floor((r.w - 2 * pad + gap) / (tile + gap)));
    const rows = Math.max(1, Math.floor(
      (r.h - head - pad - 14 * S + gap) / (tile + gap)));

    return { head, pad, tile, gap, cols, rows, slots: cols * rows };
  }

  function tilePos(r, g, slot) {
    const i = slot % g.slots;
    return {
      x: r.x + g.pad + (i % g.cols) * (g.tile + g.gap),
      y: r.y + g.head + Math.floor(i / g.cols) * (g.tile + g.gap),
    };
  }

  function drawEndpointLane(ctx, r, title, endpoint, lane, w, S, border, note) {
    panel(ctx, r, border, title, C.frame_label, S);

    // endpoint name (or 'aliases task' note) on the title row, right-aligned
    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
    ctx.fillStyle = note ? C.amber : C.text_dim;
    const name = endpoint || (note ? '' : '<auto>');
    ctx.fillText(clip(ctx, note ? `${name} ${note}` : name, r.w * 0.62),
                 r.x + r.w - 9 * S, r.y + 11 * S);

    // content area beneath the title
    const head = Math.round(28 * S);
    const padS = Math.round(9 * S);
    const gap  = Math.round(6 * S);
    const cx   = r.x + padS;
    const cy   = r.y + head;
    const cw   = r.w - 2 * padS;
    const ch   = r.h - head - Math.round(6 * S);

    // Split: table height fits 1 header + N rows; the rest is graph.
    const rowH = Math.round(13 * S);
    const wantTable = (POOL_TABLE_ROWS + 1) * rowH + Math.round(6 * S);
    const tableH = Math.min(wantTable, Math.max(0, Math.floor(ch * 0.5)));
    const graphH = Math.max(0, ch - tableH - gap);

    const color = lane === 'learning' ? C.amber : C.cyan;
    // Match the learning pool card's own outer border colour (`C.amber_dim`,
    // set by the caller in `drawHpcLanes`) so the graph plot and the
    // recent-tasks table read as one dark-orange unit inside it.  The
    // task pool keeps the neutral frame border.
    const inner = lane === 'learning' ? C.amber_dim : C.frame_border;

    if (graphH > Math.round(30 * S)) {
      drawTaskGraph(ctx, cx, cy, cw, graphH,
                    w.poolHistory[lane] || [],
                    w.t, w.counts[lane].running, color, inner, S);
    }
    if (tableH > rowH) {
      drawTaskTable(ctx, cx, cy + graphH + gap, cw, tableH, rowH,
                    w, lane, inner, S);
    }
  }

  // The task-manager graph: y-axis labelled "tasks", x-axis is time
  // (rightmost point = now), sliding window of `POOL_WINDOW` seconds.
  // Y at each x = number of concurrent tasks running at that instant,
  // drawn as the step function that comes straight out of `poolHistory`.
  function drawTaskGraph(ctx, x, y, wd, ht, hist,
                         nowT, nowRunning, color, border, S) {
    const yLabelW = Math.round(22 * S);
    const xTickH  = Math.round(12 * S);
    const plotX = x + yLabelW;
    const plotY = y + Math.round(3 * S);
    const plotW = wd - yLabelW - Math.round(4 * S);
    const plotH = ht - xTickH - Math.round(4 * S);
    if (plotW < 20 || plotH < 12) return;

    // plot background
    ctx.fillStyle = C.panel_deep;
    rr(ctx, plotX, plotY, plotW, plotH, 2 * S);
    ctx.fill();
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    rr(ctx, plotX + 0.5, plotY + 0.5, plotW - 1, plotH - 1, 2 * S);
    ctx.stroke();

    // rotated y-axis label
    ctx.save();
    ctx.translate(x + Math.round(9 * S), plotY + plotH / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = C.frame_label;
    ctx.font = `600 ${Math.round(9 * S)}px ${FONT}`;
    ctx.fillText('tasks', 0, 0);
    ctx.restore();

    // -------- data prep -----------------------------------------------
    // Snap the right edge back to the previous `POOL_STEP` boundary so
    // the graph only shifts one bucket every half-second instead of
    // scrolling continuously.
    const nBuckets = Math.round(POOL_WINDOW / POOL_STEP);
    const rightT   = Math.floor(nowT / POOL_STEP) * POOL_STEP;
    const tMin     = rightT - POOL_WINDOW;

    // Left-edge value: the running count in effect at `tMin`.  Any event
    // at or before tMin sets the value that held going into the window.
    let running = 0;
    let hi = 0;
    while (hi < hist.length && hist[hi].t <= tMin) {
      running = hist[hi].running;
      hi++;
    }

    // Per-bucket max concurrent value.  Between events the value is
    // constant, so the bucket peak is max(value_at_start, event values
    // that landed in the bucket).
    const values = new Array(nBuckets).fill(0);
    for (let b = 0; b < nBuckets; b++) {
      const bEnd = tMin + (b + 1) * POOL_STEP;
      let peakB = running;
      while (hi < hist.length && hist[hi].t < bEnd) {
        running = hist[hi].running;
        if (running > peakB) peakB = running;
        hi++;
      }
      values[b] = peakB;
    }
    // The rightmost bucket is the one still in progress: fold in the
    // live `nowRunning` too, so a spike happening right now doesn't wait
    // for the next boundary to appear.
    if (nowRunning > values[nBuckets - 1]) values[nBuckets - 1] = nowRunning;

    // -------- axes ---------------------------------------------------
    let peak = Math.max(1, nowRunning);
    for (const v of values) if (v > peak) peak = v;
    const yTop = Math.max(1, Math.ceil(peak * 1.25));

    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(8 * S)}px ${FONT_MONO}`;
    ctx.fillText(String(yTop), plotX - 3 * S, plotY + Math.round(5 * S));
    ctx.fillText('0', plotX - 3 * S, plotY + plotH - Math.round(4 * S));

    // -------- draw stepped bars --------------------------------------
    const bucketPx = plotW / nBuckets;
    const toY = v => plotY + plotH - (v / yTop) * plotH;

    // filled area under the step
    ctx.save();
    ctx.globalAlpha = 0.20;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(plotX, plotY + plotH);
    for (let b = 0; b < nBuckets; b++) {
      const bx0 = plotX + b * bucketPx;
      const bx1 = plotX + (b + 1) * bucketPx;
      const by  = toY(values[b]);
      ctx.lineTo(bx0, by);
      ctx.lineTo(bx1, by);
    }
    ctx.lineTo(plotX + plotW, plotY + plotH);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // step outline on top
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    for (let b = 0; b < nBuckets; b++) {
      const bx0 = plotX + b * bucketPx;
      const bx1 = plotX + (b + 1) * bucketPx;
      const by  = toY(values[b]);
      if (b === 0) ctx.moveTo(bx0, by);
      else {
        const pby = toY(values[b - 1]);
        if (pby !== by) ctx.lineTo(bx0, by);
      }
      ctx.lineTo(bx1, by);
    }
    ctx.stroke();
    ctx.restore();

    // x-axis ticks
    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(8 * S)}px ${FONT_MONO}`;
    ctx.fillText(`-${POOL_WINDOW}s`, plotX,
                 plotY + plotH + Math.round(2 * S));
    ctx.textAlign = 'right';
    ctx.fillText('now', plotX + plotW,
                 plotY + plotH + Math.round(2 * S));
  }

  // Recent-tasks table, capped at `POOL_TABLE_ROWS` newest.  DT hash and
  // lane are real; Kind / Inv / Task are faked from the uid because the
  // wire does not carry per-task metadata.
  function drawTaskTable(ctx, x, y, wd, ht, rowH, w, lane, border, S) {
    // border + subtle background so the table reads as its own block
    ctx.fillStyle = C.panel_deep;
    rr(ctx, x, y, wd, ht, 2 * S);
    ctx.fill();
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    rr(ctx, x + 0.5, y + 0.5, wd - 1, ht - 1, 2 * S);
    ctx.stroke();

    const padS = Math.round(6 * S);
    const cx = x + padS;
    const cw = wd - 2 * padS;

    const cols = [
      { label: 'DT',           frac: 0.12 },
      { label: 'Kind',         frac: 0.13 },
      { label: 'Agent',        frac: 0.28 },
      { label: 'Investigator', frac: 0.20 },
      { label: 'Task',         frac: 0.27 },
    ];
    const colX = [];
    let cur = cx;
    for (const c of cols) { colX.push(cur); cur += Math.round(c.frac * cw); }
    colX.push(cx + cw);   // sentinel for last-column width

    // header row
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = C.frame_label;
    ctx.font = `600 ${Math.round(8 * S)}px ${FONT}`;
    const hy = y + rowH / 2 + Math.round(2 * S);
    cols.forEach((c, i) => {
      spaced(ctx, c.label.toUpperCase(), colX[i], hy, 0.6);
    });

    // header underline (matches the outer table border colour)
    ctx.strokeStyle = border;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x + padS, y + rowH + 0.5);
    ctx.lineTo(x + wd - padS, y + rowH + 0.5);
    ctx.stroke();

    // Newest first, cap to POOL_TABLE_ROWS.
    const tasks = [...w.tasks.values()]
      .filter(t => t.lane === lane)
      .sort((a, b) => b.t0 - a.t0)
      .slice(0, POOL_TABLE_ROWS);

    if (!tasks.length) {
      ctx.textAlign = 'center';
      ctx.fillStyle = C.text_dim;
      ctx.font = `400 ${Math.round(9 * S)}px ${FONT}`;
      ctx.fillText('no tasks yet', x + wd / 2,
                   y + rowH + (ht - rowH) / 2);
      return;
    }

    ctx.font = `400 ${Math.round(8.5 * S)}px ${FONT_MONO}`;
    tasks.forEach((t, i) => {
      const ry = y + rowH + i * rowH + rowH / 2;
      if (ry + rowH / 2 > y + ht - 2) return;

      const owner = w.owners.get(t.uid);
      const attr = fakeTaskAttr(t.uid);
      const cells = [
        owner ? short(owner) : '—',
        attr.kind,
        attr.agent,
        attr.inv,
        attr.name,
      ];
      // faded once the task has ended; running tasks stay full brightness
      ctx.fillStyle = t.tEnd === null ? C.text_label : C.text_dim;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      cells.forEach((cell, j) => {
        const w2 = colX[j + 1] - colX[j] - 4 * S;
        ctx.fillText(clip(ctx, cell, w2), colX[j], ry);
      });
    });
  }

  // Placeholder task attribution: 60% Agent / 40% Utility, with an
  // investigator for the agent tasks and one of a handful of typical
  // task names for both.
  const FAKE_TASK_NAMES = [
    'infer', 'predict', 'train_window', 'active_learn', 'criterion',
    'checkpoint', 'validate', 'bootstrap', 'preprocess', 'stream_hop',
  ];
  function fakeTaskAttr(uid) {
    const h = fnv1a(uid);
    const isAgent = (Math.abs(h) % 5) < 3;          // 3/5 agent, 2/5 utility
    const kind = isAgent ? 'Agent' : 'Utility';
    const agent = isAgent
      ? FAKE_AGENTS[Math.abs(h >>> 11) % FAKE_AGENTS.length].name
      : '—';
    const inv  = isAgent
      ? FAKE_INVESTIGATORS[Math.abs(h >>> 3) % FAKE_INVESTIGATORS.length]
      : '—';
    const name = FAKE_TASK_NAMES[Math.abs(h >>> 7) % FAKE_TASK_NAMES.length];
    return { kind, agent, inv, name };
  }

  // ---- flights: the inferred verbs, and spawned tasks -------------------

  // Arcs are no longer drawn.  Twin lifecycle, calls and results all
  // read on the cards in place (state pill, agent rows, pool graph and
  // recent-task table), so the flying animations added noise for no new
  // information.  The probe still records the resolved arc geometry so
  // headless tests keep their assertions.
  function drawFlights(ctx, L, w, ui) {
    if (!ui || !ui.probe) return;

    for (const f of w.flights) {
      const k = (w.t - f.t0) / f.dur;
      if (k < 0 || k > 1) continue;

      const seg = flightPath(L, w, f);
      if (!seg) continue;

      ui.probe.arcs.push({
        kind: f.kind, label: f.label, twin: f.twinId,
        uid:  f.task ? f.task.uid : null,
        lane: f.task ? f.task.lane : null,
        owner: f.task ? (w.owners.get(f.task.uid) || null) : null,
        x0: seg.x0, y0: seg.y0, x1: seg.x1, y1: seg.y1,
        color: seg.color, k,
      });
    }
  }

  // The card a task's arc leaves from: the twin that submitted it, which the
  // service recorded at submission and the poll carried here (`applyTasks`).
  // No candidates, no heuristics -- either the uid is in the map or nothing
  // is claimed, and what is left then is a slice of the broker lane's right
  // edge.  A twin that has failed or closed *does* keep its arcs: it really
  // did submit them, and its card is still on the canvas to say so.
  //
  // Always inside the broker lane, never the client's: a task is submitted
  // by the plugin on a twin's behalf, and an arc leaving the session
  // sub-lane would say the client submitted it, which never happens.
  //
  // Resolved per frame, so an event that arrived before the poll explaining
  // it starts at the edge and snaps to the card as soon as the map lands --
  // one frame of honesty rather than a queue of held-back arcs.
  function originRect(L, w, uid) {
    const id = uid && w.owners.get(uid);
    const tw = id && w.twins.get(id);

    if (tw && tw._rect) return { rect: tw._rect, card: true };

    return { card: false,
             rect: { x: L.broker.x + L.broker.w - 1,
                     y: L.broker.y + L.broker.h * 0.4,
                     w: 1, h: L.broker.h * 0.1 } };
  }

  // Where an arc meets a twin card: on its centre line, low down -- inside
  // the card, so it belongs to exactly one of them (an edge is shared with
  // whatever sits next to it), and close enough to the bottom that the curve
  // is out from under the card almost at once.  Everything that touches a
  // card meets it here.
  function cardAnchor(r) {
    return { x: r.x + r.w / 2, y: r.y + CARD_ANCHOR * r.h };
  }

  function flightPath(L, w, f) {
    const S = L.S;

    // a spawned simulation task: its origin -> the endpoint lane's own slot
    // and, on completion, the same hop back
    if ((f.kind === 'spawn' || f.kind === 'result') && f.task) {
      const r = f.task.lane === 'learning' ? L.learning : L.inference;
      const g = laneGeom(r, S);
      const p = tilePos(r, g, f.task.slot);
      const home = originRect(L, w, f.task.uid);
      const color = f.task.lane === 'learning' ? C.amber : C.cyan;

      const at = { x: p.x + g.tile / 2, y: p.y + g.tile / 2 };
      // an unattributed task leaves the broker lane's edge instead: that rect
      // is a sliver, and `onCard` says the bow has no card to clear
      const to = cardAnchor(home.rect);

      if (f.kind === 'result') {
        return { x0: at.x, y0: at.y, x1: to.x, y1: to.y,
                 size: g.tile * 0.9,
                 color: f.task.state === 'FAILED' ? C.red : C.violet,
                 label: null, dim: 0.7, onCard: home.card };
      }
      return { x0: to.x, y0: to.y, x1: at.x, y1: at.y,
               size: g.tile * 1.1, color, label: null, onCard: home.card };
    }

    // a stream message: the publisher's tile -> the twin that published it
    if (f.kind === 'sample') {
      const pub = f.from && w.publishers.get(f.from);
      const tw = w.twins.get(f.twinId);
      if (!pub || !pub._rect || !tw || !tw._rect) return null;

      const into = cardAnchor(tw._rect);

      return {
        x0: pub._rect.x + pub._rect.w, y0: pub._rect.y + pub._rect.h / 2,
        x1: into.x, y1: into.y, onCard: true,
        size: Math.round(6 * S), color: C.green, label: null, dim: 0.85,
      };
    }

    // a create / destroy verb, inferred from the poll delta.  The client
    // frame is no longer drawn (sessions are data-only now), so `sess._rect`
    // is never set and `L.client` is a 1x1 virtual anchor on the broker's
    // left edge -- see `layout`.  Arcs therefore emerge at the broker
    // boundary as if arriving from off-canvas.
    const tw   = w.twins.get(f.twinId);
    const sess = tw && w.sessions.find(s => s.sid === tw.sid);
    const from = (sess && sess._rect) || L.client;
    const to   = (tw && tw._rect)
      || { x: L.broker.x + 20 * S, y: L.broker.y + 34 * S, w: 40 * S, h: 40 * S };

    const a = { x: from.x + from.w, y: from.y + from.h / 2 };
    const b = cardAnchor(to);
    const onCard = !!(tw && tw._rect);
    const size = Math.round(11 * S);

    if (f.kind === 'create') {
      return { x0: a.x, y0: a.y, x1: b.x, y1: b.y, size,
               color: C.cyan, label: 'create', onCard };
    }

    // A client call and the answer to it, one completed round trip.  The
    // inference round trip is the one a client is actually waiting on, so
    // both halves of it are amber -- the request colour, told apart from
    // the green a stream pulses in and the violet a task result returns in.
    if (f.kind === 'call') {
      const inference = f.label === 'get_inference';
      return { x0: a.x, y0: a.y, x1: b.x, y1: b.y,
               size: Math.round(inference ? 9 * S : 8 * S),
               color: inference ? C.amber : C.cyan, onCard,
               label: f.label, dim: inference ? 1 : 0.8 };
    }
    if (f.kind === 'answer') {
      return { x0: b.x, y0: b.y, x1: a.x, y1: a.y,
               size: Math.round(8 * S), color: C.amber, onCard,
               label: null, dim: 0.9 };
    }

    // a state report going back client-ward: dashed and dim, because
    // unlike a verb it is not a call anyone made -- it is what the next
    // `twin_list` poll would have carried
    if (f.kind === 'report') {
      return { x0: b.x, y0: b.y, x1: a.x, y1: a.y,
               size: Math.round(7 * S), onCard,
               color: STATE_TEXT[f.label] || C.text_dim,
               label: f.label, dash: true, dim: 0.7 };
    }

    return { x0: b.x, y0: b.y, x1: a.x, y1: a.y, size,
             color: C.grey, label: 'destroy', onCard };
  }

  // ---- hover tooltip: the full twin id, metrics and last error ----------

  function drawTooltip(ctx, L, w, ui) {
    if (!ui.hover) return;

    let hit = null;
    for (const tw of w.twins.values()) {
      if (tw._rect && inside(ui.hover, tw._rect)) { hit = tw; break; }
    }
    if (!hit) return;

    const S = L.S;
    const lines = [`twin    ${hit.id}`, `state   ${hit.state}`
      + (hit.age !== null ? `   age ${humanAge(hit.age)}` : ''),
      `session ${hit.sid}`];

    for (const [name, m] of Object.entries(hit.metrics || {})) {
      lines.push(`metric  ${name} = ${fmt(m.value)} `
        + `(target ${m.operator || ''} ${fmt(m.threshold)}`
        + `${m.should_stop ? ', met' : ''})`
        + (m.component ? `  ${m.component}` : ''));
    }
    const errAt = lines.length;
    if (hit.last_error) lines.push(...wrap(hit.last_error, 60));

    ctx.font = `400 ${Math.round(10 * S)}px ${FONT_MONO}`;
    let bw = 0;
    for (const line of lines) bw = Math.max(bw, ctx.measureText(line).width);

    const lh = Math.round(14 * S);
    const box = {
      w: bw + 16 * S, h: lines.length * lh + 12 * S,
      x: Math.max(L.M, Math.min(ui.hover.x + 14 * S, L.W - bw - 16 * S - L.M)),
      y: Math.max(L.hd, Math.min(ui.hover.y + 14 * S,
                                 L.H - lines.length * lh - 16 * S)),
    };

    ctx.save();
    ctx.globalAlpha = 0.97;
    ctx.fillStyle = '#0b1220';
    rr(ctx, box.x, box.y, box.w, box.h, 5 * S);
    ctx.fill();
    ctx.strokeStyle = hit.state === 'failed' ? C.red : C.frame_border;
    ctx.lineWidth = 1;
    rr(ctx, box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1, 5 * S);
    ctx.stroke();
    ctx.restore();

    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    lines.forEach((line, i) => {
      ctx.fillStyle = i === 0 ? C.text : (i >= errAt ? C.red : C.text_dim);
      ctx.fillText(line, box.x + 8 * S, box.y + 6 * S + i * lh);
    });
  }

  function wrap(text, cols) {
    const out = [];
    let line = '';
    for (const word of String(text).split(/\s+/)) {
      if ((line + ' ' + word).trim().length > cols) { out.push(line); line = word; }
      else line = line ? `${line} ${word}` : word;
    }
    if (line) out.push(line);
    return out;
  }

  function inside(p, r) {
    return p.x >= r.x && p.x <= r.x + r.w && p.y >= r.y && p.y <= r.y + r.h;
  }

  // =========================================================================
  //  DOM helpers + CSS (one <style>, injected once)
  // =========================================================================

  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function btn(html, onclick) {
    const b = el('button', 'dtd-btn');
    b.innerHTML = html;
    b.onclick = onclick;
    return b;
  }

  function label(text) { return el('span', 'dtd-label', text); }

  function range(min, max, step, value) {
    const r = document.createElement('input');
    r.type = 'range';
    r.min = String(min); r.max = String(max);
    r.step = String(step); r.value = String(value);
    r.className = 'dtd-speed';
    return r;
  }

  function input(value, placeholder, width) {
    const i = document.createElement('input');
    i.className = 'dtd-in';
    i.value = value;
    i.placeholder = placeholder;
    i.style.width = width + 'px';
    return i;
  }

  function fileInput() {
    const f = document.createElement('input');
    f.type = 'file';
    f.accept = '.json,application/json';
    f.style.display = 'none';
    return f;
  }

  function download(name, text) {
    const url = URL.createObjectURL(
      new Blob([text], { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  }

  const CSS = `
.dtd-root { display: flex; flex-direction: column; gap: 8px;
            width: 100%; height: 100%; min-height: 300px;
            font-family: ${FONT}; font-size: 13px; color: ${C.text}; }
.dtd-stage { flex: 1; min-height: 220px; position: relative;
             border-radius: 6px; overflow: hidden; background: ${C.bg}; }
.dtd-stage.dtd-drop { outline: 2px dashed ${C.cyan}; outline-offset: -4px; }
.dtd-canvas { display: block; }
.dtd-controls { display: flex; align-items: center; gap: 9px;
                flex-wrap: wrap; padding: 8px 12px; background: #0e1626;
                border: 1px solid ${C.unused_brd}; border-radius: 6px;
                box-sizing: border-box; }
.dtd-btn { background: #182030; color: ${C.text};
           border: 1px solid ${C.unused_brd}; border-radius: 4px;
           padding: 5px 12px; font-family: inherit; font-size: 12px;
           cursor: pointer; letter-spacing: 0.04em; }
.dtd-btn:hover { background: #202840; }
.dtd-btn.dtd-active { background: #3a1622; border-color: ${C.red};
                      color: ${C.red}; }
.dtd-btn.dtd-play { min-width: 92px; text-align: center; }
.dtd-spacer { flex: 1; }
.dtd-speed { width: 118px; accent-color: ${C.cyan}; vertical-align: middle; }
.dtd-label { color: ${C.text_dim}; letter-spacing: 0.08em;
             text-transform: uppercase; font-size: 10px; }
.dtd-num { font-variant-numeric: tabular-nums; min-width: 42px;
           display: inline-block; text-align: right; font-size: 11px; }
.dtd-badge { font-size: 10px; letter-spacing: 0.1em; padding: 3px 8px;
             border: 1px solid ${C.cyan}; color: ${C.cyan};
             border-radius: 3px; }
.dtd-badge.dtd-live { border-color: ${C.green}; color: ${C.green}; }
.dtd-in { background: #0b1220; color: ${C.text};
          border: 1px solid ${C.unused_brd}; border-radius: 4px;
          padding: 5px 8px; font-family: ${FONT_MONO}; font-size: 11px; }
`;

  function injectCss() {
    if (document.querySelector('style[data-dt-dash]')) return;
    const style = document.createElement('style');
    style.setAttribute('data-dt-dash', VERSION);
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  // =========================================================================
  //  PUBLIC ENTRY
  // =========================================================================

  /**
   * Mount a dashboard into `host`.
   *
   *   opts.brokerUrl  broker origin for live mode ('' = same origin)
   *   opts.dtPath     the dt plugin's proxy path (default '/broker/dt')
   *   opts.token      broker token; POSTed to /auth once to mint the cookie
   *   opts.live       connect on load
   *   opts.sample     a bundled recording object to replay on load
   *   opts.compact    hide the connect form (the Explorer host does)
   */
  function mount(host, opts) {
    return newDash(host, opts || {});
  }

  window.DTDash = { mount, VERSION, SCHEMA };

})();
