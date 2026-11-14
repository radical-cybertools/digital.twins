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
# one color code for every figure: grey = a baseline without the DT (dark:
# the plain task, light: the hand-wired workflow), blue / orange = the DT
# (investigator / agent), light blue = a second DT variant or a remote path
BASE = "#4a4a4a"
BASE_LIGHT = "#a8a8a8"
DT_A = "#2a78d6"
DT_B = "#eb6834"
DT_C = "#86b7ee"
COLORS = {
    "bare": BASE,
    "investigator": DT_A,
    "agent": DT_B,
    "dt": DT_A,
    "extra": DT_C,
}
LABELS = {"bare": "bare AsyncFlow", "xgf": "hand-wired (xGFabric)"}
DASHED = set()  # series drawn dashed by lines()
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
            label=LABELS.get(name, name),
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
            label=LABELS.get(name, name),
            color=COLORS.get(name, COLORS["extra"]),
            linestyle="--" if name in DASHED else "-",
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


XGF = "xgf"  # round 3's hand-wired xGFabric-style row
COLORS[XGF] = BASE_LIGHT


def solo(pattern):
    """Round 3 runs each row in its own process: {row: [run, ...]}."""
    return {r: SRC.load(pattern.format(row=r)) for r in [*ROWS, XGF]}


def later_bursts(run, row):
    """req/s of a run's bursts 2-5, median: the first burst warms up."""
    r = run["rows"][row]
    return statistics.median(r["concurrent"] / b for b in r["bursts_s"][1:])


# ---------------------------------------------------------------- figures


def fig_e1_paths(fig):
    """E1: p50 per request and burst throughput, local pool to radical.3."""
    # round 3b (U2, U3): each row, xgf included, in its own process; the
    # service path was measured once, in round 2 (S3)
    local = solo("r3b/u2/insitu-pm-pool8-c50-solo-{row}-r*-stack-r3b-*.json")
    cross = solo("r3b/u2/insitu-pm-orbit-cross-c1-solo-{row}-r*-stack-r3b-*.json")
    remote = SRC.load("r3b/u3/insitu-pm-remote-c1-r*-stack-r3b-*.json")
    service = SRC.load("s3/service-remote-stack-*.json")[0]
    burst_local = solo("r3b/u2/insitu-pm-pool8-c500-solo-{row}-r*-stack-r3b-*.json")
    burst_cross = solo(
        "r3b/u2/insitu-pm-orbit-cross-c500-solo-{row}-r*-stack-r3b-*.json"
    )

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
            [run["rows"][r]["p50_ms"] for run in local[r]],
            [run["rows"][r]["p50_ms"] for run in cross[r]],
            row_values(remote, "p50_ms")[r] if r in ROWS else [],
            svc if r == "bare" else [],
        ]
        for r in [*ROWS, XGF]
    }
    bars(ax1, cats, p50, log=True)
    ax1.set_ylabel("p50 latency per request [ms]")
    ax1.set_title("(a) latency, sequential")
    fig.legend(
        *ax1.get_legend_handles_labels(),
        loc="outside upper center",
        ncol=4,
        frameon=False,
    )

    burst = {
        r: [
            [later_bursts(run, r) for run in burst_local[r]],
            [later_bursts(run, r) for run in burst_cross[r]],
        ]
        for r in [*ROWS, XGF]
    }
    bars(ax2, ["local\npool", "ORBIT\ncross-node"], burst)
    ax2.set_ylabel("throughput, c=500 [req/s]")
    ax2.set_title("(b) under load")


def fig_e1_pool(fig):
    """E1: burst throughput by process pool size, local pool, c=500.

    Round 3c V1: all rows in one process, five bursts each, the median of
    bursts 2-5 (a single burst depends on where the client's garbage
    collector runs, round 3b U4)."""
    pools = [1, 2, 4, 8, 16, 32, 64, 128, 256]
    vals = {r: [] for r in ROWS}
    for w in pools:
        runs = SRC.load(f"r3c/v1/insitu-pm-pool{w}-c500-r*-stack-r3c-*.json")
        for r in ROWS:
            vals[r].append([later_bursts(run, r) for run in runs])
    ax = fig.subplots()
    lines(ax, [str(w) for w in pools], vals)
    ax.set_xlabel("process pool size")
    ax.set_ylabel("throughput, c=500 [req/s]")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False)


def fig_e1_exsitu(fig):
    """E1 ex-situ: learner throughput by window size, bare vs through DT."""
    runs = SRC.load("r3b/u5/exsitu-pm-pool8-r*-stack-r3b-*.json")
    sizes = runs[0]["batch_sizes"]
    names = {
        "bare": "bare ROSE learner",
        "zmq": "bare, behind the ZMQ hop",
        "dt": "through DT",
        "dt-batched": "through DT, window as one message",
    }
    COLORS.update(
        {
            names["bare"]: BASE,
            names["zmq"]: BASE_LIGHT,
            names["dt"]: DT_A,
            names["dt-batched"]: DT_C,
        }
    )
    vals = {
        names[row]: [
            [run["rows"][row]["msg_per_s"][i] for run in runs]
            for i in range(len(sizes))
        ]
        for row in names
    }
    ax = fig.subplots()
    lines(ax, [str(s) for s in sizes], vals, log=True)
    ax.set_xlabel("samples per window")
    ax.set_ylabel("learner throughput [samples/s]")
    ax.legend(frameon=False)


def fig_e2(fig):
    """Inputs per twin: joined streams, and agents per twin (round 3)."""
    ax2, ax3 = fig.subplots(1, 2)
    join = SRC.load("r3/t4/join-pm-r*-stack-r3-*.json")
    ks = sorted(join[0]["max_sustainable"], key=int)
    ins = [[run["max_sustainable"][k]["inputs_per_s"] for run in join] for k in ks]
    lines(ax2, ks, {"dt": ins})
    ax2.set_xlabel("joined input streams")
    ax2.set_ylabel("max sustainable [inputs/s]")
    ax2.set_ylim(bottom=0)
    ax2.set_title("(a) joined streams")

    runs = SRC.load("r3/t4/agents-pm-r*-stack-r3-*.json")
    ms = [1, 2, 4, 8, 16]
    COLORS.update({"side by side": DT_A, "chained": DT_B})
    lines(
        ax3,
        [str(m) for m in ms],
        {
            label: [
                [run["max_sustainable"][f"{mode}-{m}"]["inputs_per_s"] for run in runs]
                for m in ms
            ]
            for label, mode in (("side by side", "side"), ("chained", "chain"))
        },
    )
    ax3.set_xlabel("agents in one twin")
    ax3.set_ylim(bottom=0)
    ax3.set_title("(b) agents")
    ax3.legend(frameon=False)


def fig_e4_swap(fig):
    """E4: hot-swap turnaround, and inference while models are published."""
    configs = [
        ("local\nc=1", "r3/t5/swap-pm-pool8-c1-r*-stack-r3-*.json"),
        ("local\nc=50", "r3/t5/swap-pm-pool8-c50-r*-stack-r3-*.json"),
        ("ORBIT\nc=1", "r3/t5/swap-pm-orbit-cross-c1-r*-stack-r3-*.json"),
        ("ORBIT\nc=50", "r3/t5/swap-pm-orbit-cross-c50-r*-stack-r3-*.json"),
    ]
    ax1, axp, ax2 = fig.subplots(1, 3, gridspec_kw={"width_ratios": [4, 3, 3]})
    COLORS["turnaround"] = DT_A
    bars(
        ax1,
        [c for c, _ in configs],
        {
            "turnaround": [
                [r["turnaround"]["p50_ms"] for r in SRC.load(p)] for _, p in configs
            ]
        },
        log=True,
        labels=True,
    )
    ax1.set_ylabel("to first answer, p50 [ms]")
    ax1.set_title("(a) component swap")

    # publish to first answer with the new model; the publish interval
    # (1 s, 100 ms, 10 ms) makes no difference, so its points are pooled
    paths = [
        ("local", "r3/t5/update-pm-local-pool8-r*-stack-r3-*.json"),
        ("ORBIT", "r3/t5/update-pm-orbit-cross-r*-stack-r3-*.json"),
        ("WAN", "s2/update-pm-remote-r*-stack-*.json"),
    ]
    COLORS["model update"] = DT_A
    bars(
        axp,
        [c for c, _ in paths],
        {
            "model update": [
                [p["answered"]["p50_ms"] for r in SRC.load(pt) for p in r["points"]]
                for _, pt in paths
            ]
        },
        log=True,
        labels=True,
    )
    axp.set_title("(b) model update")
    for ax in (ax1, axp):
        ax.tick_params(axis="x", labelsize=6)

    dip = SRC.load("r3/t5/dip-pm-pool8-c50-r*-stack-r3-*.json")
    pub = SRC.load("r3/t4/publish-pm-pool8-c1-r*-stack-r3-*.json")
    rates = [1.0, 10.0, 100.0]
    COLORS.update({"c=1": DT_A, "c=50": DT_C})

    def ratio(runs):
        return [
            [
                p["req_per_s_x_rate0"]
                for r in runs
                for p in r["points"]
                if p["rate_target"] == rate
            ]
            for rate in rates
        ]

    bars(ax2, ["1", "10", "100"], {"c=1": ratio(pub), "c=50": ratio(dip)})
    ax2.set_ylim(0, 1.15)
    ax2.set_xlabel("model updates / s")
    ax2.set_ylabel("throughput vs no updates")
    ax2.set_title("(c) while updating")
    ax2.set_ylim(0, 1.45)
    ax2.legend(frameon=False, ncol=2, loc="upper center", fontsize=6)


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
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw={"width_ratios": [3, 2]})
    # the session's other twin, probed while the learning endpoint is lost
    # (from the kill until the loss is reported), current stack (round 2c)
    runs = [
        ("cluster", "c2/endpoint-loss-pm-stack2c-*.json"),
        ("radical.3", "c1/endpoint-loss-remote-run*-*.json"),
    ]
    rtts, counts = [], []
    for _, pattern in runs:
        probes = [
            p
            for run in SRC.load(pattern)
            for k in run["kills"]
            for p in k.get("probes", [])
            if p["twin"] == "sibling"
        ]
        rtts.append([p["rtt"] * 1e3 for p in probes if p["ok"]])
        counts.append((sum(p["ok"] for p in probes), len(probes)))
    COLORS["in-situ inference"] = DT_A
    bars(
        ax1,
        [r[0] for r in runs],
        {"in-situ inference": rtts},
        log=True,
        err=p10_p90,
    )
    for j, (ok, n) in enumerate(counts):
        ax1.annotate(
            f"{ok}/{n}",
            (j, 1.0),
            xycoords=("data", "axes fraction"),
            ha="center",
            va="top",
            fontsize=6,
        )
    ax1.set_ylabel("latency while the endpoint\nis lost, p50 [ms]")
    ax1.set_title("(a) in-situ inference")

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
    COLORS.update({"cluster": DT_A, "radical.3": DT_C})
    bars(ax2, [lab for _, lab in keys], series, labels=True)
    ax2.set_ylabel("seconds")
    ax2.set_title("(b) recovery")
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
    COLORS.update({"A100 GPU": DT_A, "CPU node": DT_C})
    bars(ax1, cats, series, log=True)
    ax1.set_ylabel("per call [ms]")
    ax1.set_title("(a) surrogate, in-process")
    ax1.legend(frameon=False)

    # (b) round 8 R8-E: one answer through the twin on dragon_native, split
    # into its parts (medians per part over all probes of 3 runs per variant)
    parts = [
        ("framework in", None, DT_A),
        ("tar extract", "extract_s", BASE_LIGHT),
        ("model reload", "reload_s", BASE),
        ("field", "field_s", DT_C),
        ("other in task", None, "#cfcfcf"),
        ("framework out", None, DT_B),
    ]
    rows = []
    for var, vlabel in (("warm0", "reload"), ("warm1", "warm")):
        probes = [
            p
            for run in SRC.load(f"r8/r8-e/{var}/twin-r*-stack-r8-*.json")
            for p in run["probes"]
            if not p.get("error") and p.get("task")
        ]
        for arch in ("pinn", "fno"):
            ps = [p for p in probes if p.get("arch") == arch]

            def med(xs):
                xs = [x for x in xs if x is not None]
                return statistics.median(xs) * 1e3 if xs else 0.0

            t = [p["task"] for p in ps]
            inside = med([x["task_end"] - x["task_start"] for x in t])
            vals = {
                "framework in": med([x["task_start"] - p["t_send"] for p, x in zip(ps, t)]),
                "framework out": med([p["t_recv"] - x["task_end"] for p, x in zip(ps, t)]),
            }
            for label, key, _ in parts:
                if key:
                    vals[label] = med([x.get(key) for x in t])
            vals["other in task"] = max(
                0.0, inside - sum(vals[k] for k in ("tar extract", "model reload", "field"))
            )
            rows.append((f"{arch.upper()} {vlabel}", vals))
    ys = list(range(len(rows)))[::-1]
    left = [0.0] * len(rows)
    for label, _, color in parts:
        widths = [vals[label] for _, vals in rows]
        ax2.barh(ys, widths, left=left, color=color, height=0.6, label=label)
        left = [lft + w for lft, w in zip(left, widths)]
    for y, total in zip(ys, left):
        ax2.text(total + 10, y, f"{total:.0f}", va="center", fontsize=6)
    ax2.set_yticks(ys, [name for name, _ in rows])
    ax2.set_xlabel("one answer [ms]")
    ax2.set_xlim(0, max(left) * 1.15)
    ax2.grid(axis="x", color="#dddddd", linewidth=0.5)
    ax2.grid(axis="y", visible=False)
    ax2.set_title("(b) through the twin, A100, dragon_native")
    ax2.legend(frameon=False, fontsize=5.5, loc="lower right")


def fig_e3_sites(fig):
    """E3: one twin on N sites, DT service vs hand-wired, req/s (round 5,
    CPU-bound work model; across facilities with 64 client threads)."""
    loaded = {}
    for label, pattern in (
        ("DT, one site each", "r5/cpu5/sites-spread-*-r5-*.json"),
        ("DT, all on one site", "r5/cpu5/sites-one-*-r5-*.json"),
        ("hand-wired, one site each", "r5/cpu5/xgf-spread-*-r5-*.json"),
        ("hand-wired, all on one site", "r5/cpu5/xgf-one-*-r5-*.json"),
    ):
        loaded[label] = SRC.load(pattern)
    # the N values every series measured
    ns = sorted(
        set.intersection(
            *(
                {p["n"] for r in runs for p in r["points"] if "error" not in p}
                for runs in loaded.values()
            )
        )
    )
    series = {
        label: [
            [
                p["req_per_s_bursts_2_5"]
                for r in runs
                for p in r["points"]
                if p.get("n") == n and "error" not in p
            ]
            for n in ns
        ]
        for label, runs in loaded.items()
    }
    COLORS.update(
        {
            "DT, one site each": DT_A,
            "DT, all on one site": DT_C,
            "hand-wired, one site each": BASE,
            "hand-wired, all on one site": BASE_LIGHT,
        }
    )
    DASHED.update({"hand-wired, one site each", "hand-wired, all on one site"})
    ax1, ax2 = fig.subplots(1, 2, gridspec_kw={"width_ratios": [3, 2]})
    lines(ax1, [str(n) for n in ns], series)
    ax1.set_xlabel("investigators (sites)")
    ax1.set_ylabel("throughput [req/s]")
    ax1.set_ylim(bottom=0)
    ax1.set_title("(a) Perlmutter nodes")
    fig.legend(
        *ax1.get_legend_handles_labels(),
        loc="outside lower center",
        ncol=2,
        frameon=False,
        fontsize=6,
    )

    # broker and DT service on radical.3, three Perlmutter sites, the fourth
    # on radical.3
    remote = SRC.load("r5/remote64/sites-spread-r*-r5-*.json")
    COLORS["DT, through radical.3"] = DT_A
    lines(
        ax2,
        [str(n) for n in ns],
        {
            "DT, through radical.3": [
                [
                    p["req_per_s_bursts_2_5"]
                    for r in remote
                    for p in r["points"]
                    if p.get("n") == n and "error" not in p
                ]
                for n in ns
            ]
        },
    )
    ax2.set_xlabel("investigators (sites)")
    ax2.set_ylim(bottom=0)
    ax2.set_title("(b) across facilities")


def _sites_points(pattern):
    """{n: [req/s per repeat]} from bench_sites results."""
    out = {}
    for run in SRC.load(pattern):
        for p in run["points"]:
            if "error" not in p and not p.get("n_errors"):
                out.setdefault(p["n"], []).append(p["req_per_s_bursts_2_5"])
    return out


def fig_sites(fig):
    """One twin on N sites, 120 ms CPU per request, 8 workers per site
    (round 8 R8-D, dragon_native), DT service vs hand-wired."""
    dt = _sites_points("r8/r8-d/sites-n*-r*-stack-r8-*.json")
    xgf = _sites_points("r8/r8-d/xgf-n*-r*-stack-r8-*.json")
    ns = sorted(dt)
    one = statistics.median(dt[1])
    ax1, ax2 = fig.subplots(1, 2)
    for ax, scale, ylabel in (
        (ax1, 1.0, "throughput [req/s]"),
        (ax2, 1.0 / one, "speedup against one site"),
    ):
        ax.plot(ns, [n * one * scale for n in ns], color=BASE_LIGHT,
                linestyle=":", linewidth=1.0, label="ideal")
        for label, pts, color, style in (
            ("DT service", dt, DT_A, "-"),
            ("hand-wired", xgf, BASE, "--"),
        ):
            xs = sorted(pts)
            st = [spread([v * scale for v in pts[n]]) for n in xs]
            ax.errorbar(xs, [v[0] for v in st],
                        yerr=[[v[1] for v in st], [v[2] for v in st]],
                        label=label, color=color, linestyle=style, marker="o",
                        markersize=3, linewidth=1.2, elinewidth=0.6, capsize=1.5)
        ax.set_xscale("log", base=2)
        ax.set_xticks(ns, [str(n) for n in ns])
        ax.set_xlabel("sites")
        ax.set_ylabel(ylabel)
        ax.set_ylim(bottom=0)
    ax1.set_title("(a) throughput")
    ax2.set_title("(b) speedup")
    ax1.legend(frameon=False)


def fig_twins(fig):
    """N twins in one experiment on one dragon_native engine, closed loop
    (round 8 R8-2): throughput and the worst twin's p99."""
    ax1, ax2 = fig.subplots(1, 2)
    series = (
        ("no-op tasks", "r8/r8-2/engine-noop-one-r*-stack-r8-*.json", DT_A, "-"),
        ("20 ms tasks", "r8/r8-2/engine-w20-one-r*-stack-r8-*.json", DT_B, "--"),
    )
    for label, pattern, color, style in series:
        rps, p99 = {}, {}
        for run in SRC.load(pattern):
            for p in run["points"]:
                if p.get("failed") or p.get("n_create_errors"):
                    continue
                rps.setdefault(p["twins"], []).append(p["req_per_s"])
                p99.setdefault(p["twins"], []).append(p["p99_ms_max"])
        xs = sorted(rps)
        for ax, pts in ((ax1, rps), (ax2, p99)):
            st = [spread(pts[n]) for n in xs]
            ax.errorbar(xs, [v[0] for v in st],
                        yerr=[[v[1] for v in st], [v[2] for v in st]],
                        label=label, color=color, linestyle=style, marker="o",
                        markersize=3, linewidth=1.2, elinewidth=0.6, capsize=1.5)
    for ax in (ax1, ax2):
        ax.set_xscale("log", base=4)
        ax.set_xticks(xs, [str(n) for n in xs])
        ax.minorticks_off()
        ax.set_xlabel("twins in one experiment")
    ax1.set_ylabel("throughput [req/s]")
    ax1.set_ylim(bottom=0)
    ax1.set_title("(a) throughput")
    ax1.legend(frameon=False)
    ax2.axhline(1000, color=BASE_LIGHT, linestyle=":", linewidth=1.0)
    ax2.text(1, 1050, "break: 1 s", fontsize=6, color=BASE)
    logscale(ax2)
    ax2.set_ylabel("worst twin p99 [ms]")
    ax2.set_title("(b) tail latency")


# figures whose results are not in yet: rendered only with --only
PENDING = {}

FIGURES = {
    "e1-paths": (fig_e1_paths, 2.3),
    "e1-pool": (fig_e1_pool, 2.0),
    "e1-exsitu": (fig_e1_exsitu, 2.0),
    "e2-scaling": (fig_e2, 2.0),
    "e3-sites": (fig_e3_sites, 2.5),
    "e4-swap": (fig_e4_swap, 2.2),
    "e5-endpoint-loss": (fig_e5, 2.5),
    "e6-windfield": (fig_e6, 2.2),
    "sites": (fig_sites, 2.0),
    "twins": (fig_twins, 2.0),
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
        func, height = {**FIGURES, **PENDING}[name]
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
