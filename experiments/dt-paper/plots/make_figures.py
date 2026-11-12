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


XGF = "xgf"  # round 3's hand-wired xGFabric-style row
COLORS[XGF] = COLORS["extra"]


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
    ax2.set_ylabel("burst, c=500 [req/s]")
    ax2.set_title("(b) burst")


def fig_e1_inprocess(fig):
    """E1 through ORBIT: DT rows and xgf against bare, each row in its own
    process and all rows in one process, with round 2's in-process ratios."""
    rows = ["investigator", "agent", XGF]
    ax1, ax2 = fig.subplots(1, 2, sharey=True)
    for ax, c in ((ax1, 50), (ax2, 500)):
        alone = solo(
            f"r3b/u2/insitu-pm-orbit-cross-c{c}-solo-{{row}}-r*-stack-r3b-*.json"
        )
        bare = statistics.median(later_bursts(r, "bare") for r in alone["bare"])
        inproc = SRC.load(
            f"r3b/u2/insitu-pm-orbit-cross-c{c}-inproc-r*-stack-r3b-*.json"
        )
        COLORS.update(
            {
                "each row in its own process": COLORS["bare"],
                "all rows in one process": COLORS["dt"],
            }
        )
        bars(
            ax,
            ["inves-\ntigator", "agent", "xgf"],
            {
                "each row in its own process": [
                    [later_bursts(run, r) / bare for run in alone[r]] for r in rows
                ],
                "all rows in one process": [
                    [later_bursts(run, r) / later_bursts(run, "bare") for run in inproc]
                    for r in rows
                ],
            },
        )
        ax.axhline(1.0, color="#888888", linewidth=0.6, linestyle=":")
        ax.set_title(f"(%s) c={c}" % ("a" if c == 50 else "b"))
    # round 2c, one process, before finished tasks were released
    old = SRC.load("c3/p4/insitu-pm-orbit-cross-c500-r*-stack2c-*.json")
    key = "concurrent_req_per_s"
    ratios = [
        statistics.median(run["rows"][r][key] / run["rows"]["bare"][key] for run in old)
        for r in ("investigator", "agent")
    ]
    (marks,) = ax2.plot(
        [0.2, 1.2], ratios, marker="x", color="#a3352b", markersize=5, linestyle="none"
    )
    ax2.legend(
        [marks],
        ["one process, before the fix"],
        frameon=False,
        loc="lower right",
        fontsize=6,
    )
    ax1.set_ylabel("throughput vs bare")
    ax1.set_ylim(0, 1.3)
    fig.legend(
        *ax1.get_legend_handles_labels(),
        loc="outside upper center",
        ncol=2,
        frameon=False,
    )


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
    ax.set_ylabel("burst, c=500 [req/s]")
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
            names["bare"]: COLORS["bare"],
            names["zmq"]: "#1baf7a",
            names["dt"]: COLORS["dt"],
            names["dt-batched"]: COLORS["extra"],
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
    """E2: twins on one engine, and joined input streams."""
    twins = SRC.load("r3/t4/twins-pm-pool64-r*-stack-r3-*.json")
    join = SRC.load("r3/t4/join-pm-r*-stack-r3-*.json")
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
        ("local pool", "r3/t5/update-pm-local-pool8-r*-stack-r3-*.json"),
        ("ORBIT cross-node", "r3/t5/update-pm-orbit-cross-r*-stack-r3-*.json"),
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
            "ORBIT cross-node": "#1baf7a",
            "radical.3": "#7d5bbe",
        }
    )
    ax = fig.subplots()
    bars(ax, ["1 s", "100 ms", "10 ms"], series, log=True)
    ax.set_xlabel("publish interval")
    ax.set_ylabel("publish to first answer, p50 [ms]")
    ax.legend(frameon=False, ncol=3, loc="lower center", bbox_to_anchor=(0.5, 1.0))


def fig_e2_agents(fig):
    """E2: agents per twin, and twins (sessions) per broker."""
    runs = SRC.load("r3/t4/agents-pm-r*-stack-r3-*.json")
    ms = [1, 2, 4, 8, 16]
    ax1, ax2 = fig.subplots(1, 2)
    COLORS.update({"side by side": COLORS["bare"], "chained": COLORS["dt"]})
    lines(
        ax1,
        [str(m) for m in ms],
        {
            label: [
                [run["max_sustainable"][f"{mode}-{m}"]["inputs_per_s"] for run in runs]
                for m in ms
            ]
            for label, mode in (("side by side", "side"), ("chained", "chain"))
        },
    )
    ax1.set_xlabel("agents in one twin")
    ax1.set_ylabel("max sustainable [inputs/s]")
    ax1.set_ylim(bottom=0)
    ax1.set_title("(a) agents")
    ax1.legend(frameon=False)

    # one run with a stop at doubled p50 (N=1, 4), one past it (N=1, 16, 64)
    points = {}
    for run in SRC.load("r3/t4/broker-capacity-*stack-r3-*.json"):
        for p in run["points"]:
            points.setdefault(p["sessions"], []).append(p)
    ns = sorted(points)
    lines(
        ax2,
        [str(n) for n in ns],
        {"bare": [[p["req_per_s"] for p in points[n]] for n in ns]},
    )
    ax2.set_xlabel("sessions on one broker, one twin each")
    ax2.set_ylabel("aggregate [req/s]", color=COLORS["bare"])
    ax2.set_ylim(bottom=0)
    ax2.set_title("(b) broker")
    lat = ax2.twinx()
    lat.spines["right"].set_visible(True)
    lat.grid(False)
    lat.plot(
        range(len(ns)),
        [statistics.median(p["p50_ms"] for p in points[n]) for n in ns],
        color=COLORS["dt"],
        marker="s",
        markersize=3,
        linewidth=1.2,
        linestyle="--",
    )
    lat.set_ylabel("p50 [ms], dashed", color=COLORS["dt"])
    logscale(lat)


def fig_e4_swap(fig):
    """E4: hot-swap turnaround, and inference while models are published."""
    configs = [
        ("local\nc=1", "r3/t5/swap-pm-pool8-c1-r*-stack-r3-*.json"),
        ("local\nc=50", "r3/t5/swap-pm-pool8-c50-r*-stack-r3-*.json"),
        ("ORBIT\nc=1", "r3/t5/swap-pm-orbit-cross-c1-r*-stack-r3-*.json"),
        ("ORBIT\nc=50", "r3/t5/swap-pm-orbit-cross-c50-r*-stack-r3-*.json"),
    ]
    ax1, ax2 = fig.subplots(1, 2)
    COLORS["turnaround"] = COLORS["bare"]
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
    ax1.set_ylabel("to first new answer, p50 [ms]")
    ax1.set_title("(a) hot-swap")

    dip = SRC.load("r3/t5/dip-pm-pool8-c50-r*-stack-r3-*.json")
    pub = SRC.load("r3/t4/publish-pm-pool8-c1-r*-stack-r3-*.json")
    rates = [1.0, 10.0, 100.0]
    COLORS.update({"c=1": COLORS["bare"], "c=50": COLORS["dt"]})

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
    ax2.set_xlabel("models published per second")
    ax2.set_ylabel("inference req/s, vs none")
    ax2.set_title("(b) while publishing")
    ax2.legend(frameon=False, ncol=2, loc="upper center")
    ax2.set_ylim(0, 1.3)


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
        ("radical.3\nrun 1", "c1/endpoint-loss-remote-run1-*.json"),
        ("radical.3\nrun 2", "c1/endpoint-loss-remote-run2-*.json"),
        ("radical.3\nrun 3", "c1/endpoint-loss-remote-run3-*.json"),
    ]
    rtts, counts = [], []
    for _, pattern in runs:
        probes = [
            p
            for k in SRC.load(pattern)[0]["kills"]
            for p in k.get("probes", [])
            if p["twin"] == "sibling"
        ]
        rtts.append([p["rtt"] * 1e3 for p in probes if p["ok"]])
        counts.append((sum(p["ok"] for p in probes), len(probes)))
    COLORS["in-situ inference"] = COLORS["bare"]
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
    ax1.set_title("(a) in-situ inference, 10 kills per run")

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


def fig_e3_sites(fig):
    """E3: one twin on N sites (round 4), DT service vs hand-wired, req/s.

    Not in the default figure list until round 4's results exist; render
    it with `--only e3-sites`.
    """
    loaded = {}
    for label, pattern in (
        ("DT, one site each", "r4/local/sites-spread-r*-r4-*.json"),
        ("DT, all on one site", "r4/local/sites-one-r*-r4-*.json"),
        ("hand-wired, one site each", "r4/local/xgf-spread-r*-r4-*.json"),
        ("hand-wired, all on one site", "r4/local/xgf-one-r*-r4-*.json"),
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
            "DT, one site each": COLORS["bare"],
            "DT, all on one site": COLORS["dt"],
            "hand-wired, one site each": "#1baf7a",
            "hand-wired, all on one site": COLORS["extra"],
        }
    )
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

    # round 4 W3: broker and DT service on radical.3, three Perlmutter
    # sites, the fourth site on radical.3
    remote = SRC.load("r4/remote/sites-spread-r*-r4-*.json")
    COLORS["DT, through radical.3"] = COLORS["bare"]
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


# figures whose results are not in yet: rendered only with --only
PENDING = {}

FIGURES = {
    "e1-paths": (fig_e1_paths, 2.3),
    "e1-inprocess": (fig_e1_inprocess, 2.1),
    "e1-pool": (fig_e1_pool, 2.0),
    "e1-exsitu": (fig_e1_exsitu, 2.0),
    "e3-sites": (fig_e3_sites, 2.5),
    "e2-scaling": (fig_e2, 2.0),
    "e2-agents-broker": (fig_e2_agents, 2.1),
    "e4-propagation": (fig_e4, 2.1),
    "e4-swap": (fig_e4_swap, 2.1),
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
