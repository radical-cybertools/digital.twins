"""Round 8 provenance: what every result JSON records (the page's "Done when":
commits of all five repos, backend, workers per node, telemetry, file system)."""

import importlib.metadata as md
import json
import os
import platform
import socket
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DISTS = {"digitaltwin": "digitaltwin", "rhapsody": "rhapsody-py",
         "radical.orbit": "radical.orbit", "radical.asyncflow": "radical.asyncflow",
         "rose": "rose-surrogate-explorer", "dragonhpc": "dragonhpc"}


def _commit(dist):
    try:
        d = md.distribution(dist)
    except md.PackageNotFoundError:
        return None
    try:
        info = json.loads(d.read_text("direct_url.json") or "{}")
        return info.get("vcs_info", {}).get("commit_id") or d.version
    except Exception:
        return d.version


def _git(*cmd):
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), *cmd], text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def provenance(experiment, harness, args=None, **extra):
    return {
        "experiment": experiment,
        "harness": harness,
        "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": socket.gethostname(),
        "python": platform.python_version(),
        "slurm_job": os.environ.get("SLURM_JOB_ID"),
        "harness_commit": _git("rev-parse", "HEAD"),
        "harness_dirty": bool(_git("status", "--porcelain", "--", "experiments/dt-paper/r8")),
        "packages": {k: _commit(v) for k, v in DISTS.items()},
        "backend": os.environ.get("R8_BACKEND", "dragon_native"),
        "workers_per_node": os.environ.get("R8_WORKERS_PER_NODE", "default (physical cores)"),
        "telemetry": os.environ.get("R8_TELEMETRY", "on (default)"),
        "file_system": os.environ.get("R8_FS", "/pscratch"),
        "args": vars(args) if args is not None else None,
        **extra,
    }
