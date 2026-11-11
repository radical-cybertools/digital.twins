#!/usr/bin/env python3
"""Rebuild the round-2 node-hour ledger in JOURNAL-pm-20261107.md from sacct.

Every finished job of round 2 (names s1-*, s2-*, s3-*) since the start of
the round, node-hours = elapsed x nodes, running totals per account.  With
`2b` / `2c`, the round-2b / 2c jobs (names b0-* ... b3-*, c1-* ... c3-*)
into the table under the "Round 2b" / "Round 2c" heading.  With `3`, the
round-3 jobs (names r3-*) into JOURNAL-pm-20261110.md, with `3b` the
round-3b jobs (names r3b-*) into JOURNAL-pm-20261110b.md, with `3c` the
round-3c jobs (names r3c-*) into JOURNAL-pm-20261111.md.

    python experiments/dt-paper/s1/ledger.py [2b|2c|3|3b|3c]
"""

import subprocess
import sys

from pathlib import Path

JOURNAL = Path(__file__).resolve().parents[1] / "JOURNAL-pm-20261107.md"
ROUNDS = {  # round: (start, job-name prefixes, heading the table follows)
    "2": ("2026-11-06T12:50", ("s1-", "s2-", "s3-"), "## Node-hour ledger"),
    "2b": ("2026-11-07T05:30", ("b0-", "b1-", "b2-", "b3-"), "## Round 2b"),
    "2c": ("2026-11-07T20:00", ("c1-", "c2-", "c3-"), "## Round 2c"),
    "3": ("2026-11-09T13:00", ("r3-",), "## Node-hour ledger"),
    "3b": ("2026-11-10T15:00", ("r3b-",), "## Node-hour ledger"),
    "3c": ("2026-11-10T16:00", ("r3c-",), "## Node-hour ledger"),
}
JOURNALS = {"3": JOURNAL.with_name("JOURNAL-pm-20261110.md"),
            "3b": JOURNAL.with_name("JOURNAL-pm-20261110b.md"),
            "3c": JOURNAL.with_name("JOURNAL-pm-20261111.md")}
BUDGET = {"3": 25, "3b": 8, "3c": 1.5}
HEAD = ("| job | name | account | nodes | elapsed | node-h | m5290 total | m5290_g total |\n"
        "|---|---|---|---|---|---|---|---|\n")


def main() -> int:
    rnd = sys.argv[1] if len(sys.argv) > 1 else "2"
    start_t, prefixes, heading = ROUNDS[rnd]
    journal = JOURNALS.get(rnd, JOURNAL)
    out = subprocess.check_output(
        ["sacct", "-u", "merzky", "-S", start_t, "-X", "-n", "-P",
         "-o", "jobid,jobname,account,nnodes,elapsed,elapsedraw,state"], text=True)
    rows, tot = [], {"m5290": 0.0, "m5290_g": 0.0}
    for line in sorted(out.splitlines()):
        jid, name, acct, nodes, el, raw, state = line.split("|")
        if not name.startswith(prefixes) or state in ("PENDING", "RUNNING"):
            continue
        nh = int(raw) / 3600 * int(nodes)
        tot[acct] = tot.get(acct, 0.0) + nh
        rows.append(f"| {jid} | {name} | {acct} | {nodes} | {el} | {nh:.3f} | "
                    f"{tot.get('m5290', 0):.2f} | {tot.get('m5290_g', 0):.2f} |\n")
    table = HEAD + "".join(rows)
    text = journal.read_text()
    start = text.index(HEAD, text.index(heading))
    end = text.find("\n\n", start) + 1  # keep the blank line after the table
    end = len(text) if end == 0 else end
    journal.write_text(text[:start] + table + text[end:])
    print(f"{len(rows)} jobs; m5290 {tot['m5290']:.2f}, m5290_g {tot['m5290_g']:.2f} "
          f"node-h (of {BUDGET.get(rnd, 100)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
