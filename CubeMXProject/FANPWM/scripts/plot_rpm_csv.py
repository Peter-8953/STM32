#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Plot a FANPWM MCU CSV log.

Usage:
  python scripts\plot_rpm_csv.py logs\clean\COM4_2026_11_01.15.49.17.331.csv
  python scripts\plot_rpm_csv.py logs\COM4_*.csv --outdir data\output --dpi 120
  python scripts\plot_rpm_csv.py file.csv --seconds 0 120
"""

from __future__ import annotations

import argparse
import glob
import math
import re
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]


def load_rows(path):
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if not s or not re.match(r"^[+-]?\d", s):
                continue
            parts = s.split(",")
            if len(parts) < 10:
                continue
            try:
                vals = [float(x) for x in parts[:10]]
            except ValueError:
                continue
            if not all(math.isfinite(v) for v in vals):
                continue
            rows.append(vals)
    arr = np.asarray(rows, dtype=float)
    if arr.size == 0:
        raise ValueError(f"no usable rows in {path}")
    arr = arr[np.argsort(arr[:, 0])]
    return arr


def print_or_save(arr, path, title, outdir, dpi, start_s, end_s):
    tt = arr[:, 0] / 1000.0
    t0 = tt[0]
    tt = tt - t0
    if start_s is not None:
        mask = (tt >= start_s) & (tt <= end_s)
        arr = arr[mask]
        tt = tt[mask]
    if len(arr) < 2:
        print(f"[skip] {path.name}: too few points")
        return

    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    fig.suptitle(title, fontsize=12)

    ax = axes[0]
    ax.plot(tt, arr[:, 1], "r--", lw=1.0, label="Target RPM")
    ax.plot(tt, arr[:, 2], "b", lw=0.8, label="Actual RPM")
    ax.set_ylabel("RPM")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=9)

    ax = axes[1]
    ax.plot(tt, arr[:, 3], "g", lw=0.8, label="Duty %")
    ax.set_ylabel("Duty (%)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=9)

    ax = axes[2]
    ax.plot(tt, arr[:, 4], "m", lw=0.8, label="FF %")
    ax.plot(tt, arr[:, 5], "k", lw=0.8, label="Integral")
    ax.set_ylabel("FF / Integral")
    ax.set_xlabel("Time (s)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="best", fontsize=9)

    fig.tight_layout()
    out = Path(outdir) / (path.stem + ".png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi)
    plt.close(fig)
    print(f"[saved] {out} ({len(arr)} points)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", default=None,
                        help="CSV inputs; default logs/COM4_*.csv")
    parser.add_argument("--outdir", default=str(ROOT / "data" / "output"))
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--seconds", nargs=2, type=float,
                        metavar=("START", "END"),
                        help="Plot only [START, END] seconds")
    args = parser.parse_args()

    inputs = args.inputs or sorted(glob.glob(str(ROOT / "logs" / "COM4_*.csv")))
    if not inputs:
        raise SystemExit("No input files found.")

    start_s = args.seconds[0] if args.seconds else None
    end_s = args.seconds[1] if args.seconds else None
    for raw in inputs:
        path = Path(raw)
        try:
            arr = load_rows(path)
        except ValueError as exc:
            print(f"[skip] {path.name}: {exc}")
            continue
        print_or_save(arr, path, path.name, args.outdir, args.dpi, start_s, end_s)


if __name__ == "__main__":
    main()