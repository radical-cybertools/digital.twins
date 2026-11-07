#!/usr/bin/env python3
"""Round 2b: count stalled kills in R3 / P6 endpoint-loss results.

A kill is *stalled* when in-situ inference stopped after the learning
endpoint was killed: any learner or sibling probe failed, or the sibling's
probe after the loss was reported failed (the round-2 R3 symptom).  One line
per file, plus each stalled kill's probe errors and, where recorded
(round 2b), its UTC kill time.

    python experiments/dt-paper/s2/r3_stalls.py results/s2/endpoint-loss-*.json ...
"""

import json
import statistics
import sys

from pathlib import Path


def med(xs):
    return f"{statistics.median(xs):.1f} ({min(xs):.1f}-{max(xs):.1f})" if xs else "-"


def main() -> int:
    for f in sys.argv[1:]:
        d = json.loads(Path(f).read_text())
        kills = [k for k in d["kills"] if "error" not in k]
        stalled = [k for k in kills
                   if k["learner_answered"] < k["learner_probes"]
                   or k["sibling_answered"] < k["sibling_probes"]
                   or not k["sibling_after_ok"]]
        re = d.get("reattaches", [])
        print(f"{Path(f).name}: kills {len(kills)}/{len(d['kills'])}, "
              f"detected {sum(k['detected'] for k in kills)}, "
              f"stalled {len(stalled)}, "
              f"detect {med([k['detect_s'] for k in kills])} s, "
              f"resume {med([k['resume_s'] for k in kills])} s, "
              f"reattach {sum(bool(r.get('ok')) for r in re)}/{len(re)} "
              f"(attach {med([r['attach_s'] for r in re if r.get('ok')])} s)")
        for k in stalled:
            errs = sorted({p["error"][:90] for p in k["probes"] if not p["ok"]})
            print(f"  stalled kill {k['kill']} at {k.get('kill_utc', '?')}: {errs}")
        if kills and "kill_utc" in kills[0]:
            print("  kill times (UTC): " + ", ".join(k["kill_utc"] for k in kills))
    return 0


if __name__ == "__main__":
    sys.exit(main())
