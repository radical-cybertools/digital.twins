#!/usr/bin/env python3
"""Paper figures from the committed results.

Reads the result JSON under ``experiments/dt-paper/results/`` and writes one
PDF per figure to ``--out``, plus ``manifest.json`` (source files and the
digital_twins commit of every figure).  Only the paper stack is plotted
(rounds 2, 2b and 2c, see ``STACK.md``); round-1 results (asyncflow 0.5.1)
are not.  P8a's surrogate costs are the exception: they do not depend on
the stack.

Every point is the median over repeats; error bars span min to max.

    python3 experiments/dt-paper/plots/make_figures.py --out <paper>/figures
"""

import argparse
import glob
import json
import os
import statistics
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.normpath(os.path.join(HERE, "..", "results"))

ROWS = ["bare", "investigator", "agent"]
COLORS = {
    "bare": "#2a78d6",
    "investigator": "#eb6834",
    "agent": "#1baf7a",
    "dt": "#eb6834",
    "extra": "#7d5bbe",
}
WIDTH = 4.8  # article class text width, inches

plt.rcParams.update(
    {
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.labelsize": 8,
        "legend.fontsize": 7,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": "#dddddd",
        "grid.linewidth": 0.5,
        "pdf.fonttype": 42,
        "savefig.bbox": "tight",
    }
)


class Sources:
    """Records which result files each figure reads."""

    def __init__(self):
        self.used = {}
        self.current: str | None = None

    def load(self, pattern):
        files = sorted(glob.glob(os.path.join(RES, pattern)))
        assert files, f"no results match {pattern}"
        self.used.setdefault(self.current, []).extend(
            os.path.relpath(f, RES) for f in files
        )
        return [json.load(open(f)) for f in files]


SRC = Sources()


def spread(values):
    """Median and the distances to min and max, for errorbar()."""
    m = statistics.median(values)
    return m, m - min(values), max(values) - m


def p10_p90(values):
    """Median and the distances to the 10th and 90th percentile."""
    q = statistics.quantiles(values, n=10)
    m = statistics.median(values)
    return m, m - q[0], q[-1] - m


def logscale(ax):
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(LogLocator(subs=(1, 2, 5)))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda v, _: ""))


def bars(ax, cats, series, log=False, err=spread, labels=False):
    """Grouped bars; *series* maps a name to a list of value lists."""
    n = len(series)
    w = 0.8 / n
    for i, (name, vals) in enumerate(series.items()):
        xs = [j + (i - (n - 1) / 2) * w for j in range(len(cats))]
        keep = [j for j, v in enumerate(vals) if v]  # empty: no bar
        st = [err(vals[j]) for j in keep]
        ax.bar(
            [xs[j] for j in keep],
            [s[0] for s in st],
            w * 0.92,
            label=name,
            color=COLORS.get(name, COLORS["extra"]),
            yerr=[[s[1] for s in st], [s[2] for s in st]],
            error_kw={"elinewidth": 0.6, "capsize": 1.5},
        )
        if labels:
            for j, st_j in zip(keep, st):
                v = st_j[0]
                ax.annotate(
                    f"{v:.0f}" if v >= 10 else f"{v:.2g}",
                    (xs[j], v + st_j[2]),
                    ha="center",
                    va="bottom",
                    fontsize=6,
                    xytext=(0, 1),
                    textcoords="offset points",
                )
    ax.set_xticks(range(len(cats)), cats)
    if log:
        logscale(ax)


def lines(ax, xs, series, log=False):
    """Lines with min-max error bars; *series* maps a name to value lists."""
    for name, vals in series.items():
        st = [spread(v) for v in vals]
        ax.errorbar(
            range(len(xs)),
            [s[0] for s in st],
            yerr=[[s[1] for s in st], [s[2] for s in st]],
            label=name,
            color=COLORS.get(name, COLORS["extra"]),
            marker="o",
            markersize=3,
            linewidth=1.2,
            elinewidth=0.6,
            capsize=1.5,
        )
    ax.set_xticks(range(len(xs)), xs)
    if log:
        logscale(ax)


def row_values(runs, key):
    return {r: [run["rows"][r][key] for run in runs] for r in ROWS}


# ---------------------------------------------------------------- figures


def fig_e1_paths(fig):
    """E1: p50 per request and burst throughput, local pool to radical.3."""
    local = SRC.load("s1/p1/insitu-pm-pool8-c50-r*-stack-*.json")
    cross = SRC.load("c3/p4/insitu-pm-orbit-cross-c1-r*-stack2c-*.json")
    remote = SRC.load("c3/r1/insitu-pm-remote-c1-r*-stack2c-*.json")
    service = SRC.load("s3/service-remote-stack-*.json")[0]
    # each row in its own process: in one process the first DT row after
    # bare pays a row-order cost under the burst (journal, S1 P1)
    burst_local = {
        r: SRC.load(f"s1/p1-rerun/insitu-pm-pool8-c500-solo-{r}-r*-stack-*.json")
        for r in ROWS
    }
    burst_cross = SRC.load("c3/p4/insitu-pm-orbit-cross-c500-r*-stack2c-*.json")

    ax1, ax2 = fig.subplots(1, 2, gridspec_kw={"width_ratios": [4, 2.4]})
    cats = [
        "local\npool",
        "ORBIT\ncross-node",
        "radical.3\nclient",
        "radical.3\nservice",
    ]
    svc = [rep["p50_ms"] for rep in service["repeats"]]
    p50 = {
        r: [
            row_values(local, "p50_ms")[r],
            row_values(cross, "p50_ms")[r],
            row_values(remote, "p50_ms")[r],
            svc if r == "bare" else [],
        ]
        for r in ROWS
    }
    bars(ax1, cats, p50, log=True)
    ax1.set_ylabel("p50 latency per request [ms]")
    ax1.set_title("(a) latency, sequential")
    ax1.legend(loc="upper left", frameon=False)

    key = "concurrent_req_per_s"
    burst = {
        r: [
            [run["rows"][r][key] for run in burst_local[r]],
            row_values(burst_cross, key)[r],
        ]
        for r in ROWS
    }
    bars(ax2, ["local\npool", "ORBIT\ncross-node"], burst)
    ax2.set_ylabel("burst, c=500 [req/s]")
    ax2.set_title("(b) burst")


def fig_e1_pool(fig):
    """E1: burst throughput by process pool size, local pool, c=500."""
    pools = [1, 2, 4, 8, 16, 32, 64, 128, 256]
    key = "concurrent_req_per_s"
    vals = {r: [] for r in ROWS}
    for w in pools:
        runs = SRC.load(f"s1/p1/insitu-pm-pool{w}-c500-r*-stack-*.json")
        for r in ROWS:
            vals[r].append(row_values(runs, key)[r])
    ax = fig.subplots()
    lines(ax, [str(w) for w in pools], vals)
    ax.set_xlabel("process pool size")
    ax.set_ylabel("burst, c=500 [req/s]")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False)


def fig_e1_exsitu(fig):
    """E1 ex-situ: learner throughput by window size, bare vs through DT."""
    runs = SRC.load("s1/p3/exsitu-pm-pool8-r*-stack-*.json")
    sizes = runs[0]["batch_sizes"]
    vals = {
        name: [
            [run["rows"][row]["msg_per_s"][i] for run in runs]
            for i in range(len(sizes))
        ]
        for name, row in (("bare", "bare"), ("dt", "dt"))
    }
    COLORS.update({"bare ROSE learner": COLORS["bare"], "through DT": COLORS["dt"]})
    ax = fig.subplots()
    lines(
        ax,
        [str(s) for s in sizes],
        {"bare ROSE learner": vals["bare"], "through DT": vals["dt"]},
        log=True,
    )
    ax.set_xlabel("samples per window")
    ax.set_ylabel("learner throughput [samples/s]")
    ax.legend(frameon=False)


def fig_e2(fig):
    """E2: twins on one engine, and joined input streams."""
    twins = SRC.load("s1/p5/twins-pm-pool64-r*-stack-*.json")
    join = SRC.load("s1/p5/join-pm-r*-stack-*.json")
    ax1, ax2 = fig.subplots(1, 2)

    ns = [p["twins"] for p in twins[0]["points"]]
    agg = [[run["points"][i]["req_per_s"] for run in twins] for i in range(len(ns))]
    lines(ax1, [str(n) for n in ns], {"bare": agg})
    ax1.set_xlabel("twins on one engine")
    ax1.set_ylabel("aggregate [req/s]")
    ax1.set_ylim(bottom=0)
    ax1.set_title("(a) twins")

    ks = sorted(join[0]["max_sustainable"], key=int)
    ins = [[run["max_sustainable"][k]["inputs_per_s"] for run in join] for k in ks]
    lines(ax2, ks, {"bare": ins})
    ax2.set_xlabel("joined input streams")
    ax2.set_ylabel("max sustainable [inputs/s]")
    ax2.set_ylim(bottom=0)
    ax2.set_title("(b) joined streams")


def fig_e4(fig):
    """E4: publish of a new model to the first answer that uses it."""
    paths = [
        ("local pool", "s1/p7/update-pm-local-pool8-r*-stack-*.json"),
        ("ORBIT loopback", "s1/p7/update-pm-orbit-loop-r*-stack-*.json"),
        ("ORBIT cross-node", "s1/p7/update-pm-orbit-cross-r*-stack-*.json"),
        ("radical.3", "s2/update-pm-remote-r*-stack-*.json"),
    ]
    intervals = [1.0, 0.1, 0.01]
    series = {}
    for name, pattern in paths:
        runs = SRC.load(pattern)
        series[name] = []
        for iv in intervals:
            series[name].append(
                [
                    p["answered"]["p50_ms"]
                    for run in runs
                    for p in run["points"]
                    if p["interval_s"] == iv
                ]
            )
    COLORS.update(
        {
            "local pool": "#2a78d6",
            "ORBIT loopback": "#eb6834",
            "ORBIT cross-node": "#1baf7a",
            "radical.3": "#7d5bbe",
        }
    )
    ax = fig.subplots()
    bars(ax, ["1 s", "100 ms", "10 ms"], series, log=True)
    ax.set_xlabel("publish interval")
    ax.set_ylabel("publish to first answer, p50 [ms]")
    ax.legend(frameon=False, ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0))


def _outcomes(run):
    dead = paused = hit = ok = 0
    for k in run["kills"]:
        if k.get("sibling_after_ok") is False:
            dead += 1
        elif k["sibling_answered"] < k["sibling_probes"]:
            paused += 1
        elif "submit" in (k.get("last_error") or ""):
            hit += 1
        else:
            ok += 1
    return dead, paused, hit, ok


def fig_e5(fig):
    """E5: in-situ inference while a learning endpoint dies, and recovery."""
    runs = [
        ("r2\n1", "s2/endpoint-loss-remote-run1-stack-*.json"),
        ("r2\n2", "s2/endpoint-loss-remote-stack-*.json"),
        ("2b\n1", "b1/endpoint-loss-remote-run1-*.json"),
        ("2b\n2", "b1/endpoint-loss-remote-run2-*.json"),
        ("2b\n3", "b1/endpoint-loss-remote-run3-*.json"),
        ("2c\n1", "c1/endpoint-loss-remote-run1-*.json"),
        ("2c\n2", "c1/endpoint-loss-remote-run2-*.json"),
        ("2c\n3", "c1/endpoint-loss-remote-run3-*.json"),
    ]
    out = [_outcomes(SRC.load(p)[0]) for _, p in runs]
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw={"width_ratios": [3, 2]})
    labels = [
        "session dead",
        "paused until detection",
        "kill during a submit, answered",
        "answered",
    ]
    colors = ["#a3352b", "#e0a85c", "#1baf7a", "#2a78d6"]
    bottom = [0] * len(runs)
    for i, (lab, col) in enumerate(zip(labels, colors)):
        v = [o[i] for o in out]
        ax1.bar(range(len(runs)), v, 0.7, bottom=bottom, label=lab, color=col)
        bottom = [b + x for b, x in zip(bottom, v)]
    ax1.set_xticks(range(len(runs)), [r[0] for r in runs])
    ax1.set_ylabel("kills (of 10 per run)")
    ax1.set_title("(a) in-situ inference, radical.3")
    ax1.legend(
        frameon=False,
        fontsize=6,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        ncol=2,
    )

    cluster = SRC.load("c2/endpoint-loss-pm-stack2c-*.json")[0]
    remote = SRC.load("c1/endpoint-loss-remote-run*-stack2c-*.json")
    keys = [
        ("detect_s", "detect"),
        ("resume_s", "learning\nresumed"),
        ("attach_s", "client\nreattach"),
    ]

    def per_kill(run, key):
        items = run["reattaches"] if key == "attach_s" else run["kills"]
        return [k[key] for k in items if k.get(key) is not None]

    series = {
        "cluster": [per_kill(cluster, k) for k, _ in keys],
        "radical.3": [[v for r in remote for v in per_kill(r, k)] for k, _ in keys],
    }
    COLORS.update({"cluster": "#2a78d6", "radical.3": "#7d5bbe"})
    bars(ax2, [lab for _, lab in keys], series, labels=True)
    ax2.set_ylabel("seconds")
    ax2.set_title("(b) recovery (2c)")
    ax2.legend(frameon=False)


def fig_e6(fig):
    """E6: WindField surrogate cost, and latency through the twin."""
    ax1, ax2 = fig.subplots(1, 2)
    cats, series = [], {"A100 GPU": [], "CPU node": []}
    for model in ("pinn", "fno"):
        for what, key in (("warm", "warm_field_s"), ("reload", "reload_field_s")):
            cats.append(f"{model.upper()}\n{what}")
            series["A100 GPU"].append(
                [
                    r[key]["median"] * 1e3
                    for r in SRC.load(f"p8/surrogate-{model}-gpu-r*-dbg.json")
                ]
            )
            series["CPU node"].append(
                [
                    r[key]["median"] * 1e3
                    for r in SRC.load(f"p8/surrogate-{model}-cpu-r*-cpu3.json")
                ]
            )
    COLORS.update({"A100 GPU": "#1baf7a", "CPU node": "#2a78d6"})
    bars(ax1, cats, series, log=True)
    ax1.set_ylabel("per call [ms]")
    ax1.set_title("(a) surrogate, in-process")
    ax1.legend(frameon=False)

    twin = SRC.load("b3/p8b-twin-pm-stack2b-*.json")[0]
    arch = [("na", "no model\nyet"), ("pinn", "PINN"), ("fno", "FNO")]
    probes = {
        a: [
            p["latency_s"] * 1e3
            for p in twin["probes"]
            if p.get("arch") == a and not p.get("error")
        ]
        for a, _ in arch
    }
    COLORS["through twin"] = "#eb6834"
    bars(
        ax2,
        [lab for _, lab in arch],
        {"through twin": [probes[a] for a, _ in arch]},
        log=True,
        err=p10_p90,
        labels=True,
    )
    ax2.set_ylabel("inference latency [ms]")
    ax2.set_title("(b) through the twin, GPU (p10-p90)")


FIGURES = {
    "e1-paths": (fig_e1_paths, 2.3),
    "e1-pool": (fig_e1_pool, 2.0),
    "e1-exsitu": (fig_e1_exsitu, 2.0),
    "e2-scaling": (fig_e2, 2.0),
    "e4-propagation": (fig_e4, 2.1),
    "e5-endpoint-loss": (fig_e5, 2.5),
    "e6-windfield": (fig_e6, 2.2),
}


def main():
    ap = argparse.ArgumentParser(
        description="Paper figures from the committed results."
    )
    ap.add_argument("--out", required=True, help="directory for the PDFs")
    ap.add_argument("--only", help="comma separated figure names")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    commit = subprocess.run(
        ["git", "-C", HERE, "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    names = args.only.split(",") if args.only else list(FIGURES)
    for name in names:
        func, height = FIGURES[name]
        SRC.current = name
        fig = plt.figure(figsize=(WIDTH, height), layout="constrained")
        func(fig)
        path = os.path.join(args.out, f"{name}.pdf")
        fig.savefig(path, metadata={"CreationDate": None})  # reproducible
        plt.close(fig)
        print(path)

    manifest = os.path.join(args.out, "manifest.json")
    old = {}
    if os.path.exists(manifest):
        with open(manifest) as f:
            old = json.load(f)
    old.update(
        {n: {"digital_twins_commit": commit, "sources": SRC.used[n]} for n in names}
    )
    with open(manifest, "w") as f:
        json.dump(old, f, indent=2, sort_keys=True)
        f.write("\n")


if __name__ == "__main__":
    main()
