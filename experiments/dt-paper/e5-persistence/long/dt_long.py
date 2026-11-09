#!/usr/bin/env python3
"""E5 long run: one DT session in the broker's dt service for 30 days.

Needs a running ORBIT broker that hosts `dt` and a rhapsody inference
endpoint (`--inference`, notify window 0) that are never restarted; see
`run-long.sh`.  This driver owns everything else.

Session A, created once and kept for the whole run (its sid is in
`--state`; a restarted driver reattaches to it):

  inf   OffsetModel (inference only)
  lrn   CountingSensor -> LinearLearner, learning on the inference
        endpoint too, so A never depends on the endpoint that is killed

Session B, the daily endpoint loss (a lost engine poisons its session, R8,
so B is rebuilt after every loss):

  learner  CountingSensor -> LinearLearner, learning on `--learning`, an
           endpoint this driver starts and SIGKILLs every `--kill-every` s

Every `--probe` s: one `get_inference` per twin of A.  Every `--reattach` s:
a fresh client reattaches to A by sid and gets one answer.  Every `--stats`
s: RSS, threads and open fds of the broker and both endpoints.  Every event
is one JSON line in `--events/events-YYYYMMDD.jsonl` (UTC day);
`summarize_long.py` condenses them.

A run counts in epochs: a new epoch starts whenever session A has to be
created anew (first start, or A is gone, for example after a broker
restart).  Nothing else resets it.
"""

import argparse
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bench_endpoint_loss as bel  # noqa: E402  (registers the user modules)

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TRUTHY  # noqa: E402
from learner_components import (  # noqa: E402
    INFERENCE_DTYPE,
    SENSOR_DTYPE,
    SLOPE,
    LinearLearner,
)
from twin_components import CountingSensor  # noqa: E402

OFFSET = 7
FOREVER = 10**9  # sensor count: never runs out within the run


class Events:
    """Append-only JSON lines, one file per UTC day, safe across threads."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def __call__(self, kind, **data):
        t = time.time()
        rec = {"t": t, "utc": bel.utc(t), "kind": kind, **data}
        name = time.strftime("events-%Y%m%d.jsonl", time.gmtime(t))
        with self.lock, open(self.path / name, "a") as f:
            f.write(json.dumps(rec) + "\n")
        if kind != "probe":
            print(json.dumps(rec), flush=True)


def build_lrn(dt, twin, interval):
    dt.create_twin(twin)
    dt.add_task(twin, dt.package(CountingSensor, count=FOREVER, interval=interval),
                TRUTHY, SENSOR_DTYPE, is_persistent=True)
    dt.add_investigator(twin, dt.package(LinearLearner), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.start(twin)


def check(dt, twin, kind, timeout):
    """One probe of twin *kind* ('inf' or 'lrn'): ok, latency, error."""
    value = float(int(time.time()) % 1000)
    t0 = time.time()
    try:
        answer = bel.infer(dt, twin, value=value, timeout=timeout)
        if kind == "inf":
            ok = answer == value + OFFSET
        else:
            ok = answer["value"] == SLOPE * value
        err = None if ok else f"wrong answer: {answer!r}"[:200]
    except Exception as exc:
        ok, err = False, f"{type(exc).__name__}: {exc}"[:300]
    return {"twin": kind, "ok": ok, "rtt": time.time() - t0, "error": err}


def endpoint_pattern(name):
    # the interpreter's own command line, not the tmux or shell wrapper
    return rf"^\S*python\S* \S*radical-orbit-endpoint.py -n {name}( |$)"


def proc_stats(pattern=None, pid=None):
    """RSS, threads and open fds of *pid*, or of the oldest process whose
    command line matches *pattern*."""
    if pid is None:
        try:
            out = subprocess.check_output(["pgrep", "-of", "--", pattern], text=True)
            pid = int(out.split()[0])
        except Exception:
            return None
    try:
        status = Path(f"/proc/{pid}/status").read_text().splitlines()
        fields = dict(line.split(":", 1) for line in status if ":" in line)
        return {"pid": pid,
                "rss_kb": int(fields["VmRSS"].split()[0]),
                "threads": int(fields["Threads"]),
                "fds": len(os.listdir(f"/proc/{pid}/fd"))}
    except Exception as exc:
        return {"pid": pid, "error": str(exc)[:200]}


class SessionA:
    """The long-lived session, reattached by sid across driver restarts."""

    def __init__(self, args, events):
        self.args = args
        self.events = events
        self.state_file = Path(args.state)
        self.runtime = None
        self.dt = None
        self.state = (json.loads(self.state_file.read_text())
                      if self.state_file.exists() else {"epoch": 0})

    def save(self):
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2))
        tmp.replace(self.state_file)

    def connect(self):
        """Client runtime plus session A: reattach if possible, else create."""
        if self.runtime is not None:
            try:
                self.runtime.stop()
            except Exception:
                pass
        self.runtime = EndpointRuntime(broker_url=self.args.broker)
        self.runtime.start(wait=True)

        sid = self.state.get("sid")
        if sid:
            for attempt in range(self.args.reattach_tries):
                try:
                    t0 = time.time()
                    dt = self.runtime.get_plugin("broker", "dt", sid=sid)
                    states = {k: dt.twin(self.state[k])["state"] for k in ("inf", "lrn")}
                    self.dt = dt
                    self.events("session_a_reattached", sid=sid, epoch=self.state["epoch"],
                                attach_s=time.time() - t0, states=states)
                    return
                except Exception as exc:
                    self.events("session_a_reattach_failed", sid=sid, attempt=attempt,
                                error=f"{type(exc).__name__}: {exc}"[:300])
                    time.sleep(10)
            self.events("session_a_lost", sid=sid, epoch=self.state["epoch"])

        cfg = bel.engines(inference=self.args.inference)
        t0 = time.time()
        dt = self.runtime.get_plugin("broker", "dt", config=cfg)
        inf, lrn = str(uuid.uuid4()), str(uuid.uuid4())
        bel.build_sibling(dt, inf, offset=OFFSET)
        build_lrn(dt, lrn, self.args.sensor_interval)
        bel.await_learned(dt, lrn, self.args.learn_timeout)
        self.dt = dt
        self.state = {"epoch": self.state["epoch"] + 1, "sid": dt.sid,
                      "inf": inf, "lrn": lrn, "created_utc": bel.utc(t0)}
        self.save()
        self.events("session_a_created", ready_s=time.time() - t0, **self.state)


class Reattacher:
    """A fresh client, as a user coming back: attach by sid, one answer."""

    def __init__(self, args, events, state):
        self.args, self.events, self.state = args, events, state

    def once(self):
        t0 = time.time()
        runtime = EndpointRuntime(broker_url=self.args.broker)
        try:
            runtime.start(wait=True)
            dt = runtime.get_plugin("broker", "dt", sid=self.state["sid"])
            t_attach = time.time() - t0
            state = dt.twin(self.state["inf"])["state"]
            probe = check(dt, self.state["inf"], "inf", self.args.probe_timeout)
            self.events("reattach", ok=probe["ok"] and state == "running",
                        attach_s=t_attach, first_answer_s=time.time() - t0,
                        state=state, error=probe["error"], epoch=self.state["epoch"])
        except Exception as exc:
            self.events("reattach", ok=False, error=f"{type(exc).__name__}: {exc}"[:300],
                        epoch=self.state.get("epoch"))
        finally:
            try:
                runtime.stop()
            except Exception:
                pass


class LossCycle(threading.Thread):
    """Session B and the learning endpoint: start, learn, kill, detect, repeat."""

    def __init__(self, args, events, stop):
        super().__init__(daemon=True, name="loss-cycle")
        self.args, self.events, self.stop = args, events, stop
        self.ep = bel.LearningEndpoint(args)
        # session B's sid while it exists: persistent sessions never expire,
        # so one a crashed driver left behind is dropped by the next
        self.b_file = Path(args.state).with_name("session-b.json")

    def run(self):
        runtime = EndpointRuntime(broker_url=self.args.broker)
        runtime.start(wait=True)
        # an endpoint left over from a previous driver would never be killed
        killed = subprocess.run(
            ["pkill", "-KILL", "-f", "--", endpoint_pattern(self.args.learning)],
            check=False).returncode == 0
        if killed:
            # until the broker declares it lost, a restart under the same
            # name would bind the dead entry
            deadline = time.time() + self.args.lost_timeout
            while self.args.learning in runtime.topology() and time.time() < deadline:
                time.sleep(1)
            self.events("stale_endpoint_killed", endpoint=self.args.learning)
        if self.b_file.exists():
            sid = json.loads(self.b_file.read_text())["sid"]
            try:
                bel.drop(runtime.get_plugin("broker", "dt", sid=sid))
                self.events("stale_session_b_dropped", sid=sid)
            except Exception as exc:
                self.events("stale_session_b_gone", sid=sid, error=str(exc)[:300])
            self.b_file.unlink()
        cycle = 0
        try:
            while not self.stop.is_set():
                try:
                    self.cycle(runtime, cycle)
                except Exception as exc:
                    self.events("cycle_failed", cycle=cycle,
                                error=f"{type(exc).__name__}: {exc}"[:500])
                    self.ep.stop()
                    self.stop.wait(60)
                cycle += 1
        finally:
            self.ep.stop()
            runtime.stop()

    def cycle(self, runtime, k):
        args = self.args
        t_start = time.time()
        t_up = self.ep.start(runtime)
        cfg = bel.engines(inference=args.inference, learning=args.learning)
        dt = runtime.get_plugin("broker", "dt", config=cfg)
        self.b_file.write_text(json.dumps({"sid": dt.sid}))
        learner = str(uuid.uuid4())
        try:
            bel.build_learner(dt, learner)
            bel.await_learned(dt, learner, args.learn_timeout)
            self.events("learning_resumed", cycle=k, endpoint_up_s=t_up,
                        resume_s=time.time() - t_start, sid=dt.sid)

            # learning runs until the next scheduled kill
            if self.stop.wait(args.kill_every):
                return
            t_kill = time.time()
            self.ep.kill()
            self.events("endpoint_killed", cycle=k, endpoint=args.learning)
            entry = None
            while time.time() - t_kill < args.lost_timeout:
                entry = dt.twin(learner)
                if entry["state"] == "failed":
                    break
                time.sleep(0.5)
            detected = entry is not None and entry["state"] == "failed"
            self.events("loss_detected" if detected else "loss_not_detected", cycle=k,
                        detect_s=time.time() - t_kill,
                        last_error=entry and entry.get("last_error"))
        finally:
            bel.drop(dt)
            self.b_file.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", default="dt_long_inf")
    p.add_argument("--learning", default="dt_long_learn")
    p.add_argument("--broker-pattern",
                   default=r"^\S*python\S* \S*radical-orbit-broker.py .*--port 8011( |$)",
                   help="pgrep pattern for the broker's stats")
    p.add_argument("--probe", type=float, default=10.0)
    p.add_argument("--probe-timeout", type=float, default=30.0)
    p.add_argument("--reattach", type=float, default=3600.0)
    p.add_argument("--reattach-tries", type=int, default=30,
                   help="tries, 10 s apart, before session A counts as lost")
    p.add_argument("--stats", type=float, default=900.0)
    p.add_argument("--kill-every", type=float, default=86400.0,
                   help="seconds of learning between learning-endpoint kills")
    p.add_argument("--sensor-interval", type=float, default=1.0,
                   help="sensor period of session A's learner twin")
    p.add_argument("--rebuild-after", type=int, default=3,
                   help="consecutive failed probes before the client is rebuilt")
    p.add_argument("--learn-timeout", type=float, default=300.0)
    p.add_argument("--lost-timeout", type=float, default=120.0)
    p.add_argument("--state", required=True)
    p.add_argument("--events", required=True)
    p.add_argument("--logs", required=True, help="learning endpoint logs")
    args = p.parse_args()

    events = Events(args.events)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    prov = bel.provenance(args)
    prov.update(experiment="E5 long run", harness=Path(__file__).name,
                backend="orbit, concurrent on both endpoints, dt service")
    events("driver_start", host=socket.gethostname(), python=platform.python_version(),
           provenance=prov)
    a = SessionA(args, events)
    a.connect()
    loss = LossCycle(args, events, stop)
    loss.start()

    next_reattach = time.time() + args.reattach
    next_stats = time.time()
    failures = 0
    while not stop.is_set():
        t0 = time.time()
        for kind in ("inf", "lrn"):
            rec = check(a.dt, a.state[kind], kind, args.probe_timeout)
            events("probe", epoch=a.state["epoch"], **rec)
            failures = 0 if rec["ok"] else failures + 1
        if failures >= 2 * args.rebuild_after:
            events("client_rebuild", failures=failures)
            try:
                a.connect()
                failures = 0
            except Exception as exc:
                events("client_rebuild_failed", error=f"{type(exc).__name__}: {exc}"[:300])

        if time.time() >= next_reattach:
            Reattacher(args, events, a.state).once()
            next_reattach += args.reattach
        if time.time() >= next_stats:
            events("stats", broker=proc_stats(args.broker_pattern),
                   inference=proc_stats(endpoint_pattern(args.inference)),
                   learning=proc_stats(endpoint_pattern(args.learning)),
                   driver=proc_stats(pid=os.getpid()))
            next_stats += args.stats
        stop.wait(max(0.0, args.probe - (time.time() - t0)))

    loss.join(timeout=60)  # drops session B and stops the learning endpoint
    events("driver_stop")


if __name__ == "__main__":
    main()
