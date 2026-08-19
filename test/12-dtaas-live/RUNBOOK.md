# DTaaS live demo — operator runbook

Roles: radical.3 hosts the broker (+ `dt` plugin) and both rhapsody
endpoints; the laptop runs the client and the browser.  Four terminals
on radical.3 are overkill — broker and endpoints can live in one tmux.

## Once, before demo day

    # radical.3
    ~/.radical/orbit/    broker_cert.pem  broker_key.pem (0600)  broker.token
    ./deploy/install.sh broker      ~/ve-dtaas

    # laptop (already true for ve3, listed for completeness)
    ~/.radical/orbit/    broker_cert.pem  broker.token

The install script prints the version stamp — compare it across hosts
BEFORE demo day.  The digitaltwin version reads `0.0.1` on every commit,
so only the pinned install guarantees the trees match.

## Demo day, radical.3 (tmux, three panes)

    # pane 1 -- broker + dt plugin
    ./deploy/run-broker.sh ~/ve-dtaas

    # pane 2 + 3 -- the two endpoints (order after the broker)
    ./deploy/run-endpoint.sh dt_task_ep   localhost ~/ve-dtaas
    ./deploy/run-endpoint.sh dt_exsitu_ep localhost ~/ve-dtaas

Sanity: pane 1 shows `registered as 'dt_task_ep'` and `'dt_exsitu_ep'`.

## Demo day, laptop -- BEFORE the audience arrives

1. Browser: open `https://95.217.193.116:8000/`, accept the self-signed
   cert, enter the token.  This mints the cookie the dashboard rides;
   skipping it means a 401 at the worst possible moment.
2. Open `https://95.217.193.116:8000/broker/dt/ui` full-window — the
   standalone dashboard.  Check the version badge next to the stream
   pill reads 0.5.0.
3. Second tab, loaded and paused: the bundled recording
   (`src/digitaltwin/service/ui/index.html`) — the fallback.  One
   keystroke away, never mentioned unless needed.
4. Terminal -- NOTE: the client venv (`./deploy/install.sh client`,
   python 3.12 like the service; NOT the 3.13 dev venv `ve3`, which the
   service would reject for version skew):

       source ~/ve-dtaas/bin/activate
       cd test/12-dtaas-live
       export RADICAL_ORBIT_BROKER_URL=wss://95.217.193.116:8000
       export RADICAL_ORBIT_BROKER_CERT=$HOME/.radical/orbit/broker_cert.radical3.pem
       export DT_TASK_ENDPOINT=dt_task_ep DT_EXSITU_ENDPOINT=dt_exsitu_ep

   ('radical.3' is only an ssh alias -- the client and browser use the IP.
   The CERT is the BROKER's cert, fetched once via
   `scp radical.3:.radical/orbit/broker_cert.pem
        ~/.radical/orbit/broker_cert.radical3.pem`:
   each host generated its own self-signed pair, and the client pins the
   broker's, not its own.)

## The show

    python run_me.py            # steps 1-8, Enter-paced; EXITS at step 8
    python run_me.py --attach session.XXXXXXXX     # steps 9-10

Step 8 prints the exact --attach line — leave the terminal visible so
the "client is gone, twins are not" beat lands, give it ~30s while the
dashboard keeps moving, then reattach.

Talking anchors per step live in run_me.py itself; the two on-screen
proofs worth pointing at explicitly:

  - EchoSink line `served_by: dt_task_ep, trained_on: dt_exsitu_ep`
    -- in-situ and ex-situ on different hardware, printed by the twin.
  - The convergence bar on twin B's card -- ROSE's fit_error criterion,
    updated per training window (~15s cadence).

## If it goes sideways

  - Dashboard 401 -> the cookie step was skipped; do step 1 above.
  - Client dies with "TLS verification failed ... self-signed
    certificate" -> the pinned cert is the laptop's own, not the
    broker's; re-fetch it (see the scp line above).
  - Twin fails with "No module named 'opentelemetry'" -> the endpoint
    venv predates the rhapsody[telemetry] pin; `pip install
    'opentelemetry-sdk>=1.20.0' nvidia-ml-py` into it (no restart
    needed -- the next session init retries the import).
  - Twin stuck `initializing`, error mentions "Broker URL required"
    -> broker was started without RADICAL_ORBIT_BROKER_URL; restart
    pane 1 via run-broker.sh (it sets it).
  - No pulses in the sensors lane, tiles present -> the venv predates
    the orbit SSE fix (radical.orbit#113); rerun `deploy/install.sh
    broker` (fresh venv, pinned deps) and restart the broker.
  - Anything else -> tab 2, resume the recording, keep narrating.
