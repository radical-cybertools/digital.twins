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
 *  there is one model and not two.  `test/unit/test_ui_recording.py`
 *  checks the bundled sample against this schema, so the two stay in sync.
 * ========================================================================*/

(() => {

  const VERSION = '0.1.0';
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
  const TASK_COLOR = {
    RUNNING:   C.cyan,
    DONE:      C.green,
    COMPLETED: C.green,
    FAILED:    C.red,
    CANCELED:  C.grey,
  };

  // -------------------------------------------------------------------------
  //  Timings, in seconds of *model* time (the replay speed scales them all)
  // -------------------------------------------------------------------------
  const POLL_INTERVAL = 1.0;    // admin/sessions poll period, live mode
  const FLIGHT        = 1.0;    // create / destroy / spawn arc duration
  const FADE          = 0.9;    // completed task tile fade-out
  const MARKER_TTL    = 2.6;    // state-transition marker lifetime
  const PULSE_TTL     = 0.7;    // stream pulse ring lifetime
  const GLOW          = 0.5;    // on-landing halo
  const SPARK_MAX     = 24;     // sparkline points kept per metric
  const TASK_MAX      = 400;    // tile slots per endpoint lane

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
      endpoints: { task: null, exsitu: null, alias: true },
      tasks:     new Map(), // uid -> {uid, lane, state, t0, tEnd, slot}
      counts:    { task: zeroCount(), exsitu: zeroCount() },
      flights:   [],
      markers:   [],
      snapshots: 0,
      events:    0,
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

    w.sessions = sessions.map(s => ({
      sid:      s.sid || '?',
      owner:    s.owner || null,
      age:      num(s.age),
      lifetime: s.lifetime || null,
      active:   s.active !== false,
      engines:  Array.isArray(s.engines) ? s.engines : [],
      twins:    (s.twins || []).map(t => t.twin_id),
    }));

    // Engine endpoints.  The lanes are *roles*: a deployment where one
    // endpoint serves both still gets two lanes -- the ex-situ one then
    // says it aliases the task one, which is the truth on the wire.
    let task = null, exsitu = null, sawExsitu = false;
    for (const s of sessions) {
      const eps = s.endpoints || {};
      task   = task   || eps.task   || null;
      exsitu = exsitu || eps.exsitu || null;
      if (eps.exsitu) sawExsitu = true;
    }
    w.endpoints = { task, exsitu, alias: sessions.length > 0 && !sawExsitu };

    for (const s of sessions) {
      for (const t of (s.twins || [])) {
        const id = t.twin_id;
        if (!id) continue;
        seen.add(id);
        upsertTwin(w, s, t);
      }
    }

    for (const [id, tw] of w.twins) {
      if (seen.has(id) || tw.gone !== null) continue;
      tw.gone = w.t;
      flight(w, 'destroy', id);
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
        flight(w, 'create', id);
        marker(w, id, 'create', C.cyan);
      }
    } else if (tw.state !== t.state) {
      tw.prev   = tw.state;
      tw.tState = w.t;
      marker(w, id, t.state, STATE_TEXT[t.state] || C.text_dim);
    }

    tw.sid        = s.sid;
    tw.state      = t.state;
    tw.last_error = t.last_error || null;
    tw.age        = num(t.age);
    tw.gone       = null;
    applyMetrics(tw, t.metrics);
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

  // Which role lane an endpoint belongs to.  Roles, not hosts: under an
  // aliased deployment both roles report the same endpoint and everything
  // lands on `task` -- and the ex-situ lane says exactly that.
  function laneOf(w, endpoint) {
    if (endpoint && w.endpoints.exsitu && endpoint === w.endpoints.exsitu) {
      return 'exsitu';
    }
    return 'task';
  }

  function applyTask(w, endpoint, t) {
    const uid = t && t.uid;
    if (!uid) return;

    const state = String(t.state || 'RUNNING').toUpperCase();
    let task = w.tasks.get(uid);

    if (!task) {
      const lane = laneOf(w, endpoint);
      task = { uid, lane, state, t0: w.t, tEnd: null, slot: nextSlot(w, lane) };
      w.tasks.set(uid, task);
      flight(w, 'spawn', null, task);
      w.counts[lane].running++;
    }

    if (task.state !== state) {
      task.state = state;
      if (TASK_TERMINAL.has(state)) {
        task.tEnd = w.t;
        const c = w.counts[task.lane];
        c.running = Math.max(0, c.running - 1);
        if (state === 'FAILED') c.failed++;
        else if (state !== 'CANCELED') c.done++;
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
  // attributable to the exact twin and dtype that produced it.
  function applyStream(w, topic) {
    const parts = String(topic).split('/');
    if (parts.length < 4 || parts[0] !== 'dt') return;

    const tw = w.twins.get(parts[1]);
    if (tw) tw.pulse = { t: w.t, label: parts[3].replace(/\|$/, '') };
  }

  // ---- inferred verbs: arcs and markers -----------------------------------

  function flight(w, kind, twinId, task) {
    w.flights.push({ kind, twinId, task, t0: w.t });
    if (w.flights.length > 200) w.flights.shift();
  }

  function marker(w, twinId, label, color) {
    w.markers.push({ twinId, label, color, t0: w.t });
    if (w.markers.length > 80) w.markers.shift();
  }

  function expire(w) {
    w.flights = w.flights.filter(f => w.t - f.t0 < FLIGHT + 0.1);
    w.markers = w.markers.filter(m => w.t - m.t0 < MARKER_TTL);

    for (const [uid, t] of w.tasks) {
      if (t.tEnd !== null && w.t - t.tEnd > FADE) w.tasks.delete(uid);
    }
    for (const [id, tw] of w.twins) {
      if (tw.gone !== null && w.t - tw.gone > FLIGHT + FADE) w.twins.delete(id);
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

  // The live stack: a 1 Hz `admin/sessions` poll plus the gateway's SSE
  // feed.  Both are turned into the same frames a recording holds, which
  // is what makes `Record` a memcpy rather than a second serializer.
  function LiveSource(opts, sink, onStatus) {
    const broker = (opts.brokerUrl || '').replace(/\/$/, '');
    const dtPath = (opts.dtPath || '/broker/dt').replace(/\/$/, '');
    const url    = path => `${broker}${path}`;

    let timer = null, es = null, stopped = false, polls = 0, fails = 0;

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
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        sink({ kind: 'snapshot', data: await resp.json() });
        polls++;
        fails = 0;
        onStatus(`live · ${broker || 'same origin'} · ${polls} polls`, true);
      } catch (exc) {
        fails++;
        onStatus(`poll failed (${fails}): ${exc.message}`, false);
      }
    }

    function events() {
      es = new EventSource(url('/events'), { withCredentials: true });
      es.onmessage = ev => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        if (msg && msg.topic === 'notification') {
          sink({ kind: 'event', data: msg.data });
        }
      };
      es.onerror = () => onStatus('event stream interrupted', false);
    }

    return {
      mode:   'live',
      broker: broker || location.origin,
      advance() {},                  // frames arrive when they arrive
      async start() {
        await auth();
        if (stopped) return;
        await poll();
        timer = setInterval(poll, POLL_INTERVAL * 1000);
        events();
      },
      stop() {
        stopped = true;
        if (timer) clearInterval(timer);
        if (es) es.close();
        timer = es = null;
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
    let W = 0, H = 0, dpr = 1;

    const sink = frame => {
      ingest(world, frame);
      if (capture) {
        capture.frames.push({
          t: round(world.t - capture.t0, 3),
          kind: frame.kind,
          data: frame.data,
        });
      }
    };

    // ---- controls ---------------------------------------------------------

    const $play     = btn('&#10074;&#10074; pause', () => setPlaying(!playing));
    $play.classList.add('dtd-play');
    const $speedLbl = label('speed');
    const $speed    = range(0.25, 8, 0.05, 1);
    const $speedVal = el('span', 'dtd-num', '1.00×');
    const $mode     = el('span', 'dtd-badge', 'IDLE');
    const $rec      = btn('&#9679; rec', toggleRecord);
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

    function toggleRecord() {
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
        setStatus(`recorded ${rec.frames.length} frames`, true);
        return;
      }

      capture = {
        t0: world.t, iso: new Date().toISOString(),
        broker: (source && source.broker) || '', frames: [],
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
    resize();

    cv.addEventListener('mousemove', e => {
      const r = cv.getBoundingClientRect();
      hover = { x: e.clientX - r.left, y: e.clientY - r.top };
    });
    cv.addEventListener('mouseleave', () => { hover = null; });

    // ---- frame loop -------------------------------------------------------

    let last = performance.now();
    let raf  = requestAnimationFrame(frame);

    function frame() {
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

      render(ctx, W, H, world, { status, hover });
      raf = requestAnimationFrame(frame);
    }

    // ---- start ------------------------------------------------------------

    setMode('idle');
    if (opts.live) connect();
    else if (opts.sample) play(opts.sample);
    else setStatus('load a recording, or connect to a broker', false);

    return {
      world:  () => world,
      play,
      connect,
      setStatus,
      destroy() {
        cancelAnimationFrame(raf);
        ro.disconnect();
        reset();
        root.remove();
      },
    };
  }

  // =========================================================================
  //  RENDER
  // =========================================================================

  function render(ctx, W, H, w, ui) {
    const L = layout(W, H);

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);

    drawHeader(ctx, L, w, ui);
    drawClientLane(ctx, L, w);
    drawBrokerLane(ctx, L, w);
    drawHpcLanes(ctx, L, w);
    drawFlights(ctx, L, w);
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

    const cw = Math.max(Math.round(140 * S), Math.round(inner * 0.20));
    const hw = Math.max(Math.round(230 * S), Math.round(inner * 0.33));
    const bw = inner - cw - hw;

    const client = { x: M,                     y: top, w: cw, h: height };
    const broker = { x: M + cw + G,            y: top, w: bw, h: height };
    const hpc    = { x: M + cw + G + bw + G,   y: top, w: hw, h: height };

    // the HPC super-frame holds the two endpoint role lanes, stacked
    const head = Math.round(26 * S);
    const subH = Math.floor((hpc.h - head - G - Math.round(7 * S)) / 2);
    const task = { x: hpc.x + Math.round(8 * S), y: hpc.y + head,
                   w: hpc.w - Math.round(16 * S), h: subH };
    const exsitu = { x: task.x, y: task.y + subH + G, w: task.w, h: subH };

    return { S, M, G, hd, W, H, client, broker, hpc, task, exsitu };
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
      pill(ctx, x, cy - 7 * S, 'stream broker down', C.red, S);
    }

    ctx.textAlign = 'right';
    ctx.font = `400 ${Math.round(10.5 * S)}px ${FONT_MONO}`;
    ctx.fillStyle = ui.status.ok ? C.text_dim : C.amber;
    ctx.fillText(clip(ctx,
      `${ui.status.text}   |   ${w.twins.size} twins · ${w.tasks.size} tasks`
      + `   |   t = ${w.t.toFixed(1)} s`, L.W * 0.55),
      L.W - L.M, cy);
  }

  // ---- CLIENT lane: one sub-frame per session ----------------------------

  function drawClientLane(ctx, L, w) {
    const S = L.S, r = L.client;
    panel(ctx, r, C.frame_border, 'client', C.frame_label, S);

    if (!w.sessions.length) {
      placeholder(ctx, r, 'no sessions', S);
      return;
    }

    const head = Math.round(26 * S);
    const pad  = Math.round(8 * S);
    const n    = w.sessions.length;
    const room = r.h - head - pad;
    const cardH = Math.min(Math.round(62 * S),
                           Math.floor((room - (n - 1) * 6 * S) / n));

    w.sessions.forEach((s, i) => {
      const y = r.y + head + i * (cardH + 6 * S);
      if (cardH < 22 * S || y + cardH > r.y + r.h - pad * 0.5) return;

      const box = { x: r.x + pad, y, w: r.w - 2 * pad, h: cardH };
      s._rect = box;
      panel(ctx, box, s.active ? C.cyan_dim : C.grey_dim, null, null, S,
            C.panel_deep);

      const px = box.x + 8 * S, maxW = box.w - 16 * S;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'top';

      ctx.fillStyle = C.text;
      ctx.font = `600 ${Math.round(11 * S)}px ${FONT_MONO}`;
      ctx.fillText(clip(ctx, short(s.sid), maxW), px, box.y + 6 * S);

      ctx.fillStyle = C.text_dim;
      ctx.font = `400 ${Math.round(9.5 * S)}px ${FONT}`;
      ctx.fillText(clip(ctx, s.owner ? `owner ${s.owner}` : 'owner unknown',
                        maxW), px, box.y + 22 * S);

      const age = s.age === null ? '' : `age ${humanAge(s.age)}  ·  `;
      ctx.fillText(clip(ctx, `${age}${s.twins.length} twin`
                        + `${s.twins.length === 1 ? '' : 's'}`, maxW),
                   px, box.y + 34 * S);

      if (cardH > 54 * S && s.engines.length) {
        ctx.fillStyle = C.frame_label;
        ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
        ctx.fillText(clip(ctx, `engines ${s.engines.join(', ')}`, maxW),
                     px, box.y + 46 * S);
      }
    });
  }

  function placeholder(ctx, r, text, S) {
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(11 * S)}px ${FONT}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, r.x + r.w / 2, r.y + r.h / 2);
  }

  // ---- BROKER lane: the twin cards are the centrepiece -------------------

  function drawBrokerLane(ctx, L, w) {
    const S = L.S, r = L.broker;
    panel(ctx, r, C.cyan_dim, 'broker · dt plugin', C.frame_label, S);

    const twins = [...w.twins.values()].sort((a, b) => a.born - b.born);
    if (!twins.length) {
      placeholder(ctx, r, 'no twins', S);
      return;
    }

    const head = Math.round(28 * S);
    const pad  = Math.round(9 * S);
    const gap  = Math.round(8 * S);

    const cols = Math.max(1, Math.min(3,
      Math.floor((r.w - 2 * pad + gap) / (178 * S + gap))));
    // as many rows as the twins need, capped by what fits: a handful of
    // twins then get tall cards (room for their metrics) rather than short
    // ones with an empty lane underneath
    const fits = Math.max(1,
      Math.floor((r.h - head - pad + gap) / (104 * S + gap)));
    const rows = Math.min(fits, Math.ceil(twins.length / cols));
    const cardW = Math.floor((r.w - 2 * pad - (cols - 1) * gap) / cols);
    const cardH = Math.min(Math.round(150 * S),
      Math.floor((r.h - head - pad - (rows - 1) * gap) / rows));

    // centre the grid in whatever is left of the lane
    const gridH = rows * cardH + (rows - 1) * gap;
    const top = r.y + head
      + Math.max(0, Math.floor((r.h - head - pad - gridH) / 2));

    const shown = Math.min(twins.length, cols * rows);
    for (let i = 0; i < shown; i++) {
      const box = {
        x: r.x + pad + (i % cols) * (cardW + gap),
        y: top + Math.floor(i / cols) * (cardH + gap),
        w: cardW, h: cardH,
      };
      twins[i]._rect = box;
      drawTwinCard(ctx, box, twins[i], w, S);
    }
    for (let i = shown; i < twins.length; i++) twins[i]._rect = null;

    if (twins.length > shown) {
      ctx.fillStyle = C.text_dim;
      ctx.font = `400 ${Math.round(10 * S)}px ${FONT}`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText(`+${twins.length - shown} more`,
                   r.x + r.w - pad, r.y + r.h - 4 * S);
    }
  }

  function drawTwinCard(ctx, box, tw, w, S) {
    const state = tw.state || 'initializing';
    const closing = tw.gone !== null;

    let alpha = 1;
    if (closing) alpha = Math.max(0, 1 - (w.t - tw.gone) / (FLIGHT + FADE));
    else if (w.t - tw.fresh < 0.4) alpha = (w.t - tw.fresh) / 0.4;
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
    let y = box.y + 7 * S;

    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = C.text;
    ctx.font = `600 ${Math.round(12 * S)}px ${FONT_MONO}`;
    ctx.fillText(short(tw.id), px, y);

    pill(ctx, box.x + box.w - 9 * S - pillWidth(ctx, state, S), y - 1,
         state, STATE_TEXT[state] || C.text_dim, S);
    y += 20 * S;

    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
    const badge = w.backend ? `  [${w.backend}]` : '';
    ctx.fillText(clip(ctx, `ns dt/${short(tw.id)}/…${badge}`, maxW), px, y);
    y += 12 * S;

    if (tw.age !== null) {
      ctx.fillStyle = C.frame_label;
      ctx.font = `400 ${Math.round(9 * S)}px ${FONT}`;
      let line = `age ${humanAge(tw.age)}`;
      if (tw.pulse && w.t - tw.pulse.t < PULSE_TTL * 3) {
        line += `  ·  stream ${tw.pulse.label}`;
      }
      ctx.fillText(clip(ctx, line, maxW), px, y);
      y += 13 * S;
    }

    if (state === 'failed' && tw.last_error) {
      ctx.fillStyle = C.red;
      ctx.font = `400 ${Math.round(9 * S)}px ${FONT}`;
      ctx.fillText(clip(ctx, tw.last_error, maxW), px, y);
      y += 13 * S;
    }

    // convergence criteria: one block per learner metric
    for (const [name, m] of Object.entries(tw.metrics || {})) {
      const h = Math.round(34 * S);
      if (y + h > box.y + box.h - 4 * S) break;
      drawMetric(ctx, px, y, maxW, h, name, m, tw.spark.get(name) || [], S);
      y += h + 4 * S;
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

  // A criterion metric: a value bar with the target tick on it, the name,
  // the value, and a sparkline.  Which side of the target is *good* comes
  // from the learner's own comparison operator -- nothing here guesses.
  function drawMetric(ctx, x, y, wd, ht, name, m, hist, S) {
    const good  = metricGood(m);
    const color = good ? C.green : C.amber;
    const barW  = Math.round(7 * S);
    const scale = metricScale(m, hist);

    ctx.fillStyle = C.unused;
    rr(ctx, x, y, barW, ht, 2 * S);
    ctx.fill();
    ctx.strokeStyle = C.unused_brd;
    ctx.lineWidth = 1;
    rr(ctx, x + 0.5, y + 0.5, barW - 1, ht - 1, 2 * S);
    ctx.stroke();

    // the value, rising from the bottom
    if (typeof m.value === 'number') {
      const fh = Math.max(1, Math.min(ht, (m.value / scale) * ht));
      ctx.globalAlpha *= 0.5;
      ctx.fillStyle = color;
      rr(ctx, x, y + ht - fh, barW, fh, 2 * S);
      ctx.fill();
      ctx.globalAlpha /= 0.5;
      ctx.fillStyle = color;
      rr(ctx, x - 1 * S, y + ht - fh - 1, barW + 2 * S, 2, 1);
      ctx.fill();
    }

    // the target
    if (typeof m.threshold === 'number') {
      const th = Math.max(0, Math.min(ht, (m.threshold / scale) * ht));
      ctx.save();
      ctx.globalAlpha *= 0.75;
      ctx.strokeStyle = C.text;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x - 2 * S, y + ht - th + 0.5);
      ctx.lineTo(x + barW + 2 * S, y + ht - th + 0.5);
      ctx.stroke();
      ctx.restore();
    }

    const tx = x + barW + 7 * S;
    const tw = wd - barW - 7 * S;

    ctx.textAlign = 'left';
    ctx.textBaseline = 'top';
    ctx.fillStyle = C.text_label;
    ctx.font = `600 ${Math.round(9.5 * S)}px ${FONT}`;
    ctx.fillText(clip(ctx, name, tw * 0.55), tx, y);

    ctx.fillStyle = color;
    ctx.font = `400 ${Math.round(9.5 * S)}px ${FONT_MONO}`;
    ctx.textAlign = 'right';
    ctx.fillText(fmt(m.value), x + wd, y);

    ctx.textAlign = 'left';
    ctx.fillStyle = C.text_dim;
    ctx.font = `400 ${Math.round(8.5 * S)}px ${FONT_MONO}`;
    ctx.fillText(clip(ctx, `${m.operator || ''} ${fmt(m.threshold)}`
      + (m.windows ? `  ${m.windows}w` : ''), tw), tx, y + 11 * S);

    drawSpark(ctx, tx, y + 22 * S, tw, ht - 23 * S, hist, color,
              m.threshold, scale);
  }

  function metricGood(m) {
    if (typeof m.should_stop === 'boolean') return m.should_stop;
    if (typeof m.value !== 'number' || typeof m.threshold !== 'number') {
      return false;
    }
    switch (m.operator) {
      case '<':  return m.value <  m.threshold;
      case '<=': return m.value <= m.threshold;
      case '>':  return m.value >  m.threshold;
      case '>=': return m.value >= m.threshold;
      case '==': return m.value === m.threshold;
      default:   return false;
    }
  }

  // One scale for bar, tick and sparkline: the largest thing any of them
  // has to show, with the target kept comfortably inside the track.
  function metricScale(m, hist) {
    let top = 0;
    for (const v of hist) if (typeof v === 'number') top = Math.max(top, v);
    if (typeof m.value === 'number') top = Math.max(top, m.value);
    if (typeof m.threshold === 'number') top = Math.max(top, m.threshold * 1.6);
    return top > 0 ? top * 1.08 : 1;
  }

  function drawSpark(ctx, x, y, wd, ht, hist, color, threshold, scale) {
    if (wd < 12 || ht < 5) return;

    if (typeof threshold === 'number') {
      const ty = y + ht - Math.min(ht, (threshold / scale) * ht);
      ctx.save();
      ctx.globalAlpha *= 0.4;
      ctx.strokeStyle = C.text_dim;
      ctx.setLineDash([2, 2]);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, ty + 0.5);
      ctx.lineTo(x + wd, ty + 0.5);
      ctx.stroke();
      ctx.restore();
    }

    if (hist.length < 2) return;

    const step = wd / (hist.length - 1);
    ctx.save();
    ctx.globalAlpha *= 0.9;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    hist.forEach((v, i) => {
      const py = y + ht - Math.max(0, Math.min(ht, (v / scale) * ht));
      if (i === 0) ctx.moveTo(x, py);
      else ctx.lineTo(x + i * step, py);
    });
    ctx.stroke();
    ctx.restore();
  }

  // ---- HPC lanes: one per endpoint role ----------------------------------

  function drawHpcLanes(ctx, L, w) {
    const S = L.S;
    panel(ctx, L.hpc, C.frame_border, 'hpc resources', C.frame_label, S,
          C.panel_deep);

    drawEndpointLane(ctx, L.task, 'task endpoint', w.endpoints.task, 'task',
                     w, S, C.cyan_dim, null);
    drawEndpointLane(ctx, L.exsitu, 'exsitu endpoint', w.endpoints.exsitu,
                     'exsitu', w, S, C.amber_dim,
                     w.endpoints.alias ? 'aliases task' : null);
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

    const g = laneGeom(r, S);

    ctx.textAlign = 'right';
    ctx.textBaseline = 'top';
    ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
    ctx.fillStyle = note ? C.amber : C.text_dim;
    const name = endpoint || (note ? '' : '<auto>');
    ctx.fillText(clip(ctx, note ? `${name} ${note}` : name, r.w * 0.62),
                 r.x + r.w - 9 * S, r.y + 11 * S);

    for (const t of w.tasks.values()) {
      if (t.lane !== lane) continue;
      if (w.t - t.t0 < FLIGHT) continue;      // still in the air
      const p = tilePos(r, g, t.slot);
      drawTaskTile(ctx, p.x, p.y, g.tile, t, w, S);
    }

    const c = w.counts[lane];
    ctx.textAlign = 'left';
    ctx.textBaseline = 'bottom';
    ctx.font = `400 ${Math.round(9 * S)}px ${FONT_MONO}`;
    ctx.fillStyle = C.text_dim;
    ctx.fillText(clip(ctx, `${c.running} running · ${c.done} done`
      + (c.failed ? ` · ${c.failed} failed` : ''), r.w - 2 * g.pad),
      r.x + g.pad, r.y + r.h - 6 * S);
  }

  function drawTaskTile(ctx, x, y, size, t, w, S) {
    const color = TASK_COLOR[t.state] || C.cyan;
    const age = w.t - t.t0 - FLIGHT;

    let alpha = 1;
    if (t.tEnd !== null) alpha = Math.max(0, 1 - (w.t - t.tEnd) / FADE);

    // on-landing halo, then a gentle running pulse
    if (age < GLOW && t.tEnd === null) {
      const k = 1 - age / GLOW;
      ctx.save();
      ctx.shadowBlur = 14 * k * S;
      ctx.shadowColor = color;
      ctx.globalAlpha = 0.9;
      ctx.fillStyle = color;
      rr(ctx, x, y, size, size, 2);
      ctx.fill();
      ctx.fill();
      ctx.restore();
    }

    ctx.globalAlpha = alpha * (t.tEnd === null
      ? 0.8 + 0.2 * (0.5 + 0.5 * Math.sin(age * 3.0)) : 1);
    ctx.fillStyle = color;
    rr(ctx, x, y, size, size, 2);
    ctx.fill();
    ctx.globalAlpha = 1;
  }

  // ---- flights: the inferred verbs, and spawned tasks -------------------

  function drawFlights(ctx, L, w) {
    const S = L.S;

    for (const f of w.flights) {
      const k = (w.t - f.t0) / FLIGHT;
      if (k < 0 || k > 1) continue;

      const seg = flightPath(L, w, f);
      if (!seg) continue;

      const e = 1 - Math.pow(1 - k, 3);
      const mx = (seg.x0 + seg.x1) / 2;
      const my = (seg.y0 + seg.y1) / 2 - 34 * S;

      // the trail
      ctx.save();
      ctx.globalAlpha = 0.22 * (1 - k);
      ctx.strokeStyle = seg.color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(seg.x0, seg.y0);
      ctx.quadraticCurveTo(mx, my, seg.x1, seg.y1);
      ctx.stroke();
      ctx.restore();

      // the tile, along the same quadratic
      const u = 1 - e;
      const x = u * u * seg.x0 + 2 * u * e * mx + e * e * seg.x1;
      const y = u * u * seg.y0 + 2 * u * e * my + e * e * seg.y1;
      const size = seg.size * (0.65 + 0.35 * e);

      ctx.save();
      ctx.globalAlpha = 0.95;
      ctx.fillStyle = seg.color;
      rr(ctx, x - size / 2, y - size / 2, size, size, 2);
      ctx.fill();

      if (seg.label && k < 0.7) {
        ctx.globalAlpha = 0.85 * (1 - k / 0.7);
        ctx.fillStyle = seg.color;
        ctx.font = `600 ${Math.round(8.5 * S)}px ${FONT}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(seg.label, x, y - size / 2 - 2 * S);
      }
      ctx.restore();
    }
  }

  function flightPath(L, w, f) {
    const S = L.S;

    // a spawned simulation task: broker -> the endpoint lane's own slot
    if (f.kind === 'spawn' && f.task) {
      const r = f.task.lane === 'exsitu' ? L.exsitu : L.task;
      const g = laneGeom(r, S);
      const p = tilePos(r, g, f.task.slot);
      return {
        x0: L.broker.x + L.broker.w, y0: L.broker.y + L.broker.h * 0.45,
        x1: p.x + g.tile / 2,        y1: p.y + g.tile / 2,
        size: g.tile * 1.1,
        color: f.task.lane === 'exsitu' ? C.amber : C.cyan,
        label: null,
      };
    }

    // a create / destroy verb, inferred from the poll delta
    const tw   = w.twins.get(f.twinId);
    const sess = tw && w.sessions.find(s => s.sid === tw.sid);
    const from = (sess && sess._rect) || L.client;
    const to   = (tw && tw._rect)
      || { x: L.broker.x + 20 * S, y: L.broker.y + 34 * S, w: 40 * S, h: 40 * S };

    const a = { x: from.x + from.w, y: from.y + from.h / 2 };
    const b = { x: to.x, y: to.y + to.h / 2 };
    const size = Math.round(11 * S);

    if (f.kind === 'create') {
      return { x0: a.x, y0: a.y, x1: b.x, y1: b.y, size,
               color: C.cyan, label: 'create' };
    }
    return { x0: b.x, y0: b.y, x1: a.x, y1: a.y, size,
             color: C.grey, label: 'destroy' };
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
