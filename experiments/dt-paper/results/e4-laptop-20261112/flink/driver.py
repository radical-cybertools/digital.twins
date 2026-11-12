"""E4 Flink baseline driver (stdlib only; talks to the Flink REST API on localhost:8081).

  swap : path 1, code swap = stop-with-savepoint + resubmit the other jar from the savepoint
  bcast: path 2, model update via broadcast state, at a given update rate; cancelled after --dur s
"""
import argparse, json, os, re, subprocess, time, urllib.request

REST = "http://localhost:8081"


def now_ns():
    return time.time_ns()


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(REST + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        txt = r.read()
    return json.loads(txt) if txt else {}


def upload(jar):
    out = subprocess.run(["curl", "-s", "-X", "POST", "-H", "Expect:", "-F",
                          f"jarfile=@{jar}", REST + "/jars/upload"],
                         check=True, capture_output=True, text=True).stdout
    return os.path.basename(json.loads(out)["filename"])


def run_jar(jar_id, entry, args, savepoint=None, parallelism=None):
    body = {"entryClass": entry, "programArgsList": args}
    if savepoint:
        body["savepointPath"] = savepoint
    if parallelism:
        body["parallelism"] = parallelism
    return call("POST", f"/jars/{jar_id}/run", body)["jobid"]


def wait_running(jid, poll=0.002, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = call("GET", f"/jobs/{jid}")
        if j["state"] == "RUNNING" and all(v["status"] == "RUNNING" for v in j["vertices"]):
            return now_ns()
        if j["state"] in ("FAILED", "CANCELED"):
            raise RuntimeError(f"job {jid} {j['state']}")
        time.sleep(poll)
    raise TimeoutError(jid)


def stop_with_savepoint(jid, target, poll=0.002):
    trig = call("POST", f"/jobs/{jid}/stop", {"targetDirectory": target, "drain": False})["request-id"]
    while True:
        s = call("GET", f"/jobs/{jid}/savepoints/{trig}")
        if s["status"]["id"] == "COMPLETED":
            op = s["operation"]
            if "failure-cause" in op:
                raise RuntimeError(op["failure-cause"])
            return op["location"], now_ns()
        time.sleep(poll)


def wait_terminal(jid, poll=0.002):
    while call("GET", f"/jobs/{jid}")["state"] not in ("FINISHED", "CANCELED", "FAILED"):
        time.sleep(poll)
    return now_ns()


FLINK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dist", "flink-2.2.1", "bin", "flink")
CLI_ENV = dict(os.environ, JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64",
               FLINK_CONF_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf"))


def cli(*args):
    r = subprocess.run([FLINK, *args], env=CLI_ENV, capture_output=True, text=True,
                       cwd=os.path.dirname(os.path.abspath(__file__)))
    if r.returncode:
        raise RuntimeError(r.stdout + r.stderr)
    return r.stdout


def cli_stop(jid, target):
    out = cli("stop", "--savepointPath", target, jid)
    return re.search(r"Savepoint completed\. Path: (\S+)", out).group(1), now_ns()


def cli_run(jar, args, savepoint):
    out = cli("run", "-d", "-s", savepoint, "-c", "e4.SwapJob", jar, *args)
    return re.search(r"JobID ([0-9a-f]{32})", out).group(1)


def swap(a):
    os.makedirs(a.out, exist_ok=True)
    jars = [upload(os.path.join(a.jobdir, f"job-v{v}.jar")) for v in (1, 2)]
    base = now_ns() + int(3e9)
    common = ["--base", str(base), "--rate", str(a.rate), "--work-us", str(a.work_us),
              "--state-mb", str(a.state_mb), "--out", a.out]
    jid = run_jar(jars[0], "e4.SwapJob", ["--gen", "0"] + common)
    wait_running(jid)
    time.sleep(3 + a.settle)
    rec = []
    for k in range(1, a.swaps + 1):
        t_req = now_ns()
        old = jid
        if a.cli:
            sp, t_sp = cli_stop(jid, "file://" + os.path.join(a.out, "sp"))
            t_sub = now_ns()
            jid = cli_run(os.path.join(a.jobdir, f"job-v{1 + k % 2}.jar"), ["--gen", str(k)] + common, sp)
        else:
            sp, t_sp = stop_with_savepoint(jid, "file://" + os.path.join(a.out, "sp"))
            t_sub = now_ns()
            jid = run_jar(jars[k % 2], "e4.SwapJob", ["--gen", str(k)] + common, savepoint=sp)
        t_subret = now_ns()
        t_run = wait_running(jid)
        t_fin = wait_terminal(old)
        rec.append(dict(gen=k, ver=1 + k % 2, t_req=t_req, t_savepoint=t_sp, t_old_finished=t_fin,
                        t_submit=t_sub, t_submit_returned=t_subret, t_running=t_run, savepoint=sp, jobid=jid))
        print(f"swap {k}: savepoint {(t_sp-t_req)/1e6:.0f} ms, submit {(t_subret-t_sub)/1e6:.0f} ms, "
              f"running {(t_run-t_req)/1e6:.0f} ms, old finished seen {(t_fin-t_req)/1e6:.0f} ms", flush=True)
        time.sleep(a.settle)
    t_end = now_ns()
    stop_with_savepoint(jid, "file://" + os.path.join(a.out, "sp"))
    json.dump(dict(args=vars(a), base=base, t_end=t_end, swaps=rec), open(os.path.join(a.out, "driver.json"), "w"), indent=1)


def bcast(a):
    os.makedirs(a.out, exist_ok=True)
    jar = upload(os.path.join(a.jobdir, "job-v1.jar"))
    base = now_ns() + int(a.warmup * 1e9)
    args = ["--base", str(base), "--rate", str(a.rate), "--upd", str(a.upd), "--dur", str(a.dur),
            "--work-us", str(a.work_us), "--sample", str(a.sample), "--p", str(a.p),
            "--buffer-ms", str(a.buffer_ms), "--unaligned", str(a.unaligned).lower(), "--out", a.out]
    jid = run_jar(jar, "e4.BcastJob", args, parallelism=a.p)
    t_run = wait_running(jid)
    end = base + int(a.dur * 1e9)
    time.sleep(max(0, (end - now_ns()) / 1e9) + 0.5)
    call("PATCH", f"/jobs/{jid}?mode=cancel")
    while call("GET", f"/jobs/{jid}")["state"] != "CANCELED":
        time.sleep(0.05)
    json.dump(dict(args=vars(a), base=base, t_running=t_run, t_end=end, jobid=jid),
              open(os.path.join(a.out, "driver.json"), "w"), indent=1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["swap", "bcast"])
    p.add_argument("--out", required=True)
    p.add_argument("--jobdir", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--rate", type=float, default=1000)
    p.add_argument("--work-us", type=int, default=0)
    p.add_argument("--swaps", type=int, default=20)
    p.add_argument("--state-mb", type=int, default=0)
    p.add_argument("--cli", action="store_true", help="swap via bin/flink stop / run -s instead of REST")
    p.add_argument("--settle", type=float, default=4)
    p.add_argument("--upd", type=float, default=0)
    p.add_argument("--dur", type=float, default=20)
    p.add_argument("--warmup", type=float, default=5)
    p.add_argument("--sample", type=int, default=1)
    p.add_argument("--p", type=int, default=1)
    p.add_argument("--buffer-ms", type=int, default=0)
    p.add_argument("--unaligned", action="store_true")
    a = p.parse_args()
    {"swap": swap, "bcast": bcast}[a.mode](a)
