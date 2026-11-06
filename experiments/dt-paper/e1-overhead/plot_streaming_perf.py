"""Plot streaming_perf.json -> streaming_perf.png (run streaming_learner_perf.py first)."""

import json

import matplotlib.pyplot as plt

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_2 = "#52514e"
GRID = "#e4e3e0"
SERIES = {"inproc": ("#2a78d6", "in-process feed()"), "zmq": ("#eb6834", "ZMQ pub/sub (broker)")}
PANELS = {"stub": "machinery only (stubbed tasks)", "engine": "end-to-end (asyncflow, process pool)"}

with open("streaming_perf.json") as f:
    data = json.load(f)
batches = data["batch_sizes"]

fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), facecolor=SURFACE)

for ax, (mode, title) in zip(axes, PANELS.items()):
    ax.set_facecolor(SURFACE)
    for feed, (color, label) in SERIES.items():
        rates = data[f"{mode}/{feed}"]
        ax.plot(batches, rates, color=color, label=label, linewidth=2,
                marker="o", markersize=6, markeredgecolor=SURFACE, markeredgewidth=1.5)
        ax.annotate(f"{rates[-1]:,.0f}", (batches[-1], rates[-1]),
                    textcoords="offset points", xytext=(6, -3),
                    color=TEXT_2, fontsize=8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(batches)
    ax.set_xticklabels(batches)
    lo, hi = 100, 500_000  # shared scale, both panels directly comparable
    ax.set_ylim(lo, hi)
    candidates = [m * 10**e for e in range(0, 7) for m in (1, 2, 5)]
    yticks = [t for t in candidates if lo <= t <= hi]
    ax.set_yticks(yticks)
    ax.set_yticklabels([f"{t / 1000:g}k" if t >= 1000 else f"{t:g}" for t in yticks])
    ax.minorticks_off()
    ax.set_title(title, color=TEXT, fontsize=10)
    ax.set_xlabel("batch size (items per window)", color=TEXT_2, fontsize=9)
    ax.grid(True, color=GRID, linewidth=0.6)
    ax.tick_params(colors=TEXT_2, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color(GRID)

axes[0].set_ylabel("throughput (msg/s)", color=TEXT_2, fontsize=9)
axes[0].legend(frameon=False, fontsize=8, labelcolor=TEXT)

fig.suptitle("StreamingActiveLearner raw throughput", color=TEXT, fontsize=12)
fig.tight_layout()
fig.savefig("streaming_perf.png", dpi=150, facecolor=SURFACE)
print("wrote streaming_perf.png")
