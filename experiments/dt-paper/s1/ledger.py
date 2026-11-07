#!/usr/bin/env python3
"""Rebuild the round-2 node-hour ledger in JOURNAL-pm-20261107.md from sacct.

Every finished job of round 2 (names s1-*, s2-*, s3-*) since the start of
the round, node-hours = elapsed x nodes, running totals per account.

    python experiments/dt-paper/s1/ledger.py
"""

import subprocess
import sys

from pathlib import Path

JOURNAL = Path(__file__).resolve().parents[1] / "JOURNAL-pm-20261107.md"
START = "2026-11-06T12:50"
HEAD = ("| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |\n"
        "|---|---|---|---|---|---|---|---|\n")


def main() -> int:
    out = subprocess.check_output(
        ["sacct", "-u", "merzky", "-S", START, "-X", "-n", "-P",
         "-o", "jobid,jobname,account,nnodes,elapsed,elapsedraw,state"], text=True)
    rows, tot = [], {"m5290": 0.0, "m5290_g": 0.0}
    for line in sorted(out.splitlines()):
        jid, name, acct, nodes, el, raw, state = line.split("|")
        if not name.startswith(("s1-", "s2-", "s3-")) or state in ("PENDING", "RUNNING"):
            continue
        nh = int(raw) / 3600 * int(nodes)
        tot[acct] = tot.get(acct, 0.0) + nh
        rows.append(f"| {jid} | {name} | {acct} | {nodes} | {el} | {nh:.3f} | "
                    f"{tot.get('m5290', 0):.2f} | {tot.get('m5290_g', 0):.2f} |\n")
    table = HEAD + "".join(rows)
    text = JOURNAL.read_text()
    start = text.index(HEAD)
    end = text.index("\n## ", start)
    JOURNAL.write_text(text[:start] + table + text[end:])
    print(f"{len(rows)} jobs; m5290 {tot['m5290']:.2f}, m5290_g {tot['m5290_g']:.2f} "
          f"node-h (of 100)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
