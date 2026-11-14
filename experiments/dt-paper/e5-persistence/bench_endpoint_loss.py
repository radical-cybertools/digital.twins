"""E5 (partial): learning-endpoint loss and client loss, timed.

Needs a running ORBIT broker that hosts `dt` and a rhapsody inference
endpoint (`--inference`, notify window 0).  This script owns the learning
endpoint: it starts it, SIGKILLs it and restarts it.  The twins are the
integration tests' dual-engine twins (`test/integration`):

  learner   CountingSensor -> LinearLearner (ex-situ training on the
            learning endpoint, inference on the inference endpoint)
  sibling   OffsetModel (inference only), in the same session

Per endpoint kill (`--kills`):
  1. new session, both twins, wait until the learner serves a learned model
  2. SIGKILL the learning endpoint; until the learner twin reports the
     loss (`state == failed`, `last_error`), probe both twins' inference
     every `--probe` s: does in-situ inference keep answering meanwhile?
  3. restart the endpoint, wait until it advertises rhapsody, recreate the
     session (a lost engine poisons the session, see test_dt_learner R8)
     and the learner twin, and time until it serves a learned model again

Per client loss (`--reattaches`): a twin in a session, the client runtime
stops, a fresh runtime reattaches with the sid; time to reattach, twin
state, and one inference answered correctly.
"""

import argparse
import json
import os
import platform
import signal
import socket
import statistics
import subprocess
import sys
import time
import uuid

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "test" / "integration"))

from radical.orbit import EndpointRuntime  # type: ignore  # noqa: E402

from digitaltwin.components import TRUTHY, TypedData  # noqa: E402
from digitaltwin.service import register_user_modules  # noqa: E402

import learner_components  # noqa: E402
import twin_components  # noqa: E402

from learner_components import (  # noqa: E402
    INFERENCE_DTYPE,
    SENSOR_DTYPE,
    SLOPE,
    LinearLearner,
)
from twin_components import CountingSensor, OffsetModel  # noqa: E402

register_user_modules([learner_components, twin_components])

PROBE_VALUE = 3.0


# round 8 (R8-5): E5_BACKEND names the endpoints' backend (dragon_native);
# E5_LAUNCH prefixes the learning endpoint's command ("dragon -s"), which
# then starts in its own session so a kill takes its whole Dragon runtime;
# E5_CLEANUP runs after every kill ("dragon-cleanup").  Defaults: as before.
E5_BACKEND = os.environ.get("E5_BACKEND", "concurrent")


def engines(**endpoints):
    return {"engines": {name: {"endpoint_name": ep, "backends": [E5_BACKEND]}
                        for name, ep in endpoints.items()}}


def provenance(args) -> dict:
    def git(*cmd):
        try:
            return subprocess.check_output(["git", "-C", str(ROOT), *cmd],
                                           text=True).strip()
        except Exception:
            return None

    return {
        "experiment": "E5 endpoint and client loss",
        "harness": Path(__file__).name,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "digital_twins_commit": git("rev-parse", "HEAD"),
        "digital_twins_dirty": bool(git("status", "--porcelain", "--", "src")),
        "backend": f"orbit, {E5_BACKEND} on both endpoints",
        "launch": os.environ.get("E5_LAUNCH"), "cleanup": os.environ.get("E5_CLEANUP"),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "args": vars(args),
    }


class LearningEndpoint:
    """The endpoint this script kills and restarts."""

    def __init__(self, args):
        self.args = args
        self.proc = None
        self.incarnation = 0

    def start(self, runtime):
        self.incarnation += 1
        env = dict(os.environ)
        env.update({
            "RADICAL_ORBIT_LOG_FILE":
                f"{self.args.logs}/endpoint-{self.args.learning}-{self.incarnation}.log",
            "RADICAL_ORBIT_BROKER_URL": self.args.broker,
            "RADICAL_ORBIT_RHAPSODY_BACKEND": E5_BACKEND,
            "DT_TEST_ENDPOINT_TAG": self.args.learning,
        })
        log = open(f"{self.args.logs}/endpoint-{self.args.learning}-"
                   f"{self.incarnation}.console.log", "w")
        t0 = time.time()
        import shlex
        import shutil
        launch = shlex.split(os.environ.get("E5_LAUNCH", ""))
        script = shutil.which("radical-orbit-endpoint.py") if launch else "radical-orbit-endpoint.py"
        self.proc = subprocess.Popen(
            launch + [script, "-n", self.args.learning,
                      "-u", self.args.broker, "-p", "default", "--tunnel", "none"],
            env=env, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=bool(launch))
        log.close()
        deadline = t0 + 120
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"learning endpoint exited: {self.proc.returncode}")
            info = runtime.topology().get(self.args.learning) or {}
            if "rhapsody" in (info.get("plugins") or {}):
                return time.time() - t0
            time.sleep(0.25)
        raise RuntimeError("learning endpoint never advertised rhapsody")

    def kill(self):
        if os.environ.get("E5_LAUNCH"):  # the whole runtime: its process group
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            self.proc.send_signal(signal.SIGKILL)
        self.proc.wait()
        self.cleanup_s = None
        if os.environ.get("E5_CLEANUP"):
            import shlex
            t0 = time.time()
            subprocess.run(shlex.split(os.environ["E5_CLEANUP"]), timeout=180,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.cleanup_s = time.time() - t0

    def stop(self):
        if self.proc and self.proc.poll() is None and os.environ.get("E5_LAUNCH"):
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(15)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def infer(dt, twin, value=PROBE_VALUE, timeout=60.0):
    return dt.get_inference(twin, TypedData(SENSOR_DTYPE, value),
                            INFERENCE_DTYPE, timeout=timeout).data


def await_learned(dt, twin, timeout):
    deadline = time.time() + timeout
    while True:
        answer = infer(dt, twin)
        if answer["value"]:
            return answer
        if time.time() > deadline:
            raise RuntimeError(f"no learned model: {dt.twin(twin)}")
        time.sleep(0.5)


def build_learner(dt, twin):
    dt.create_twin(twin)
    dt.add_task(twin, dt.package(CountingSensor, interval=0.05),
                TRUTHY, SENSOR_DTYPE, is_persistent=True)
    dt.add_investigator(twin, dt.package(LinearLearner), SENSOR_DTYPE,
                        INFERENCE_DTYPE)
    dt.start(twin)


def build_sibling(dt, twin, offset=7):
    dt.create_twin(twin)
    dt.add_investigator(twin, dt.package(OffsetModel, offset=offset),
                        SENSOR_DTYPE, INFERENCE_DTYPE)
    dt.start(twin)


def drop(dt):
    try:
        for twin in dt.twin_list():
            dt.twin_close(twin["twin_id"])
        dt.unregister_session()
    except Exception as exc:
        print(f"session teardown: {exc}", flush=True)


def probe(dt, twin, expect, timeout):
    t0 = time.time()
    try:
        answer = infer(dt, twin, timeout=timeout)
        ok = expect(answer)
        err = None
    except Exception as exc:
        ok, err = False, f"{type(exc).__name__}: {exc}"[:200]
    return {"t": t0, "ok": ok, "rtt": time.time() - t0, "error": err}


def utc(t):
    """Epoch seconds as an ISO-8601 UTC string (to match remote broker logs)."""
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t % 1 * 1e3):03d}Z"


def kill_cycle(runtime, ep, args, k):
    cfg = engines(inference=args.inference, learning=args.learning)
    dt = runtime.get_plugin("broker", "dt", config=cfg)
    learner, sibling = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        build_sibling(dt, sibling)
        build_learner(dt, learner)
        t0 = time.time()
        first = await_learned(dt, learner, args.learn_timeout)
        t_learned = time.time() - t0

        t_kill = time.time()
        ep.kill()
        probes = []
        entry = None
        while time.time() - t_kill < args.lost_timeout:
            probes.append({"twin": "learner", **probe(
                dt, learner, lambda a: a["value"] == SLOPE * PROBE_VALUE,
                args.probe_timeout)})
            probes.append({"twin": "sibling", **probe(
                dt, sibling, lambda a: a == PROBE_VALUE + 7, args.probe_timeout)})
            entry = dt.twin(learner)
            if entry["state"] == "failed":
                break
            time.sleep(args.probe)
        t_detect = time.time() - t_kill
        detected = entry is not None and entry["state"] == "failed"
        sibling_entry = dt.twin(sibling)
        # the sibling once more, after the loss was reported
        after = probe(dt, sibling, lambda a: a == PROBE_VALUE + 7, args.probe_timeout)
    finally:
        drop(dt)

    t_restart = time.time()
    t_up = ep.start(runtime)
    dt2 = runtime.get_plugin("broker", "dt", config=cfg)
    try:
        twin2 = str(uuid.uuid4())
        build_learner(dt2, twin2)
        await_learned(dt2, twin2, args.learn_timeout)
        t_resume = time.time() - t_restart
    finally:
        drop(dt2)

    lp = [p for p in probes if p["twin"] == "learner"]
    sp = [p for p in probes if p["twin"] == "sibling"]
    rec = {
        "kill": k,
        "first_learned_s": t_learned,
        "trained_on": first.get("trained_on"),
        "detected": detected,
        "detect_s": t_detect,
        "kill_t": t_kill,
        "kill_utc": utc(t_kill),
        "detect_utc": utc(t_kill + t_detect),
        "restart_utc": utc(t_restart),
        "last_error": entry and entry.get("last_error"),
        "learner_probes": len(lp),
        "learner_answered": sum(p["ok"] for p in lp),
        "sibling_probes": len(sp),
        "sibling_answered": sum(p["ok"] for p in sp),
        "sibling_state": sibling_entry.get("state"),
        "sibling_after_ok": after["ok"],
        "endpoint_up_s": t_up,
        "cleanup_s": getattr(ep, "cleanup_s", None),
        "resume_s": t_resume,
        "probes": probes,
    }
    print(f"kill {k}: at {rec['kill_utc']}, detect {t_detect:.1f}s ({rec['last_error']}); "
          f"learner answered {rec['learner_answered']}/{len(lp)}, sibling "
          f"{rec['sibling_answered']}/{len(sp)} (after: {after['ok']}); "
          f"endpoint up {t_up:.1f}s, learning resumed {t_resume:.1f}s",
          flush=True)
    return rec


def reattach_cycle(args, k):
    first = EndpointRuntime(broker_url=args.broker)
    first.start(wait=True)
    dt = first.get_plugin("broker", "dt", config=engines(inference=args.inference))
    sid = dt.sid
    twin = str(uuid.uuid4())
    build_sibling(dt, twin, offset=k)
    assert infer(dt, twin) == PROBE_VALUE + k
    first.stop()
    time.sleep(args.gap)

    t0 = time.time()
    runtime = EndpointRuntime(broker_url=args.broker)
    runtime.start(wait=True)
    try:
        again = runtime.get_plugin("broker", "dt", sid=sid)
        t_attach = time.time() - t0
        state = again.twin(twin)["state"]
        answer = infer(again, twin)
        t_answer = time.time() - t0
        ok = again.sid == sid and state == "running" and answer == PROBE_VALUE + k
        drop(again)
    finally:
        runtime.stop()
    print(f"reattach {k}: attach {t_attach:.2f}s, first answer {t_answer:.2f}s, "
          f"state {state}, ok {ok}", flush=True)
    return {"reattach": k, "attach_s": t_attach, "first_answer_s": t_answer,
            "state": state, "ok": ok}


def med(xs):
    xs = [x for x in xs if x is not None]
    return {"median": statistics.median(xs), "min": min(xs), "max": max(xs),
            "n": len(xs)} if xs else None


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--broker", required=True)
    p.add_argument("--inference", required=True)
    p.add_argument("--learning", default="dt_p6_learning_ep")
    p.add_argument("--kills", type=int, default=10)
    p.add_argument("--reattaches", type=int, default=10)
    p.add_argument("--gap", type=float, default=2.0,
                   help="seconds between client stop and reattach")
    p.add_argument("--probe", type=float, default=0.5)
    p.add_argument("--probe-timeout", type=float, default=5.0)
    p.add_argument("--learn-timeout", type=float, default=120.0)
    p.add_argument("--lost-timeout", type=float, default=120.0)
    p.add_argument("--logs", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    results = {"provenance": provenance(args), "kills": [], "reattaches": []}
    runtime = EndpointRuntime(broker_url=args.broker)
    runtime.start(wait=True)
    ep = LearningEndpoint(args)
    try:
        results["first_endpoint_up_s"] = ep.start(runtime)
        for k in range(args.kills):
            try:
                results["kills"].append(kill_cycle(runtime, ep, args, k))
            except Exception as exc:
                print(f"kill {k} FAILED: {exc}", flush=True)
                results["kills"].append({"kill": k, "error": str(exc)[:500]})
                ep.stop()
                ep.start(runtime)
            Path(args.out).write_text(json.dumps(results, indent=2))
        for k in range(args.reattaches):
            try:
                results["reattaches"].append(reattach_cycle(args, k))
            except Exception as exc:
                print(f"reattach {k} FAILED: {exc}", flush=True)
                results["reattaches"].append({"reattach": k, "error": str(exc)[:500]})
            Path(args.out).write_text(json.dumps(results, indent=2))
    finally:
        ep.stop()
        runtime.stop()

    ks = [r for r in results["kills"] if "error" not in r]
    rs = [r for r in results["reattaches"] if "error" not in r]
    results["summary"] = {
        "kills_ok": len(ks), "kills": args.kills,
        "detect_s": med([r["detect_s"] for r in ks if r["detected"]]),
        "resume_s": med([r["resume_s"] for r in ks]),
        "endpoint_up_s": med([r["endpoint_up_s"] for r in ks]),
        "sibling_all_answered": all(r["sibling_answered"] == r["sibling_probes"]
                                    for r in ks),
        "reattaches_ok": sum(r["ok"] for r in rs), "reattaches": args.reattaches,
        "attach_s": med([r["attach_s"] for r in rs]),
        "first_answer_s": med([r["first_answer_s"] for r in rs]),
    }
    Path(args.out).write_text(json.dumps(results, indent=2))
    print(json.dumps(results["summary"], indent=2))


if __name__ == "__main__":
    main()
