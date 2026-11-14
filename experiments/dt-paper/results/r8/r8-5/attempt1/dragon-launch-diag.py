import subprocess, sys, time, os
for new in ("pg",):
    t0 = time.time()
    out = open(f"/pscratch/sd/m/merzky/dt-pm8/diag/out-{new}.log", "w")
    p = subprocess.Popen(["dragon", "-s", "/pscratch/sd/m/merzky/dt-pm8/diag/hello.py"],
                         stdout=out, stderr=subprocess.STDOUT, process_group=0)
    try:
        rc = p.wait(90)
    except subprocess.TimeoutExpired:
        rc = "timeout"; p.kill()
    print(f"start_new_session={new}: rc={rc} after {time.time()-t0:.1f}s; log: {open(out.name).read()[-300:]!r}", flush=True)
    subprocess.run(["dragon-cleanup"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
# kill test: start again in its own process group, killpg after 20 s, count leftovers
import signal
p = subprocess.Popen(["dragon", "-s", "/pscratch/sd/m/merzky/dt-pm8/diag/hello.py"], process_group=0,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5); os.killpg(p.pid, signal.SIGKILL); p.wait()
left = subprocess.run("ps -u $USER -o args= | grep -c '[d]ragon'", shell=True, capture_output=True, text=True).stdout.strip()
subprocess.run(["dragon-cleanup"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
left2 = subprocess.run("ps -u $USER -o args= | grep -c '[d]ragon'", shell=True, capture_output=True, text=True).stdout.strip()
print(f"killpg: dragon processes left {left}, after dragon-cleanup {left2}", flush=True)
