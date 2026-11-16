#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze MCU RPM sweep / step-response logs.

Input: raw terminal capture files that contain MCU CSV rows, e.g.
  logs/COM4_YYYY_MM_DD.HH.MM.SS.mmm.csv

The script:
1. Extracts and validates numeric CSV rows.
2. Writes a cleaned, normalized CSV into logs/clean/.
3. Computes sweep steady-state summaries.
4. Computes step-response metrics for each target transition.

Usage examples:
  python scripts/analyze_rpm_test.py
  python scripts/analyze_rpm_test.py logs/COM4_2026_11_01.15.35.11.924.csv
  python scripts/analyze_rpm_test.py logs/*.csv --outdir data/output --clean-dir logs/clean
  python scripts/analyze_rpm_test.py path.csv --stable-seconds 8 --plot
"""

from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import re
import statistics
from pathlib import Path
from typing import Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CSV_HEADER = ["tick", "target_rpm", "actual_rpm", "duty", "ff", "integral", "ccr",
              "per", "rpm_min", "rpm_max"]


# --------------------------------------------------------------------------- #
# Parsing / cleaning
# --------------------------------------------------------------------------- #
def is_valid_row(values: list[float]) -> bool:
    tick, target, actual, duty, ff, integral, ccr, per, rpm_min, rpm_max = values
    if not all(math.isfinite(v) for v in values):
        return False
    if tick < 1000 or tick > 2_000_000:
        return False
    if target < 0 or target > 5000:
        return False
    if actual < 0 or actual > 6000:
        return False
    if duty < 0 or duty > 100:
        return False
    if ff < 0 or ff > 100:
        return False
    if integral < -100 or integral > 100:
        return False
    if ccr < 0 or ccr > 10000:
        return False
    if per <= 0 or per > 10000:
        return False
    if rpm_min < 0 or rpm_max < rpm_min or rpm_max > 6000:
        return False
    return True


def parse_raw_log(path: Path) -> tuple[np.ndarray, dict]:
    """Return clean (N, 10) array plus parsing statistics."""
    rows: list[list[float]] = []
    seen_ticks: set[int] = set()
    total_numeric = 0
    skipped = 0
    bad_ranges = 0
    duplicates = 0
    last_bad_examples: list[str] = []

    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if not s or not re.match(r"^[+-]?\d", s):
                continue
            cols = s.split(",")
            if len(cols) < 10:
                skipped += 1
                continue
            try:
                values = [float(x) for x in cols[:10]]
            except ValueError:
                skipped += 1
                continue
            total_numeric += 1
            if not is_valid_row(values):
                bad_ranges += 1
                if len(last_bad_examples) < 5:
                    last_bad_examples.append(s)
                continue
            tick = int(values[0])
            if tick in seen_ticks:
                duplicates += 1
                continue
            seen_ticks.add(tick)
            rows.append(values)

    if not rows:
        raise ValueError(f"No valid numeric CSV rows found in {path}")

    arr = np.asarray(rows, dtype=float)
    # ensure chronological order by tick
    order = np.argsort(arr[:, 0])
    arr = arr[order]

    stats = {
        "input": str(path),
        "numeric_rows_seen": total_numeric,
        "valid_rows": len(arr),
        "skipped_malformed_rows": skipped,
        "rejected_range_rows": bad_ranges,
        "duplicate_ticks_removed": duplicates,
        "bad_examples": last_bad_examples,
    }
    return arr, stats


def write_clean_csv(arr: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for row in arr:
            writer.writerow([
                int(row[0]),
                f"{row[1]:.1f}",
                f"{row[2]:.1f}",
                f"{row[4]:.2f}",
                f"{row[5]:.2f}",
                f"{row[6]:.2f}",
                int(row[7]) if math.isfinite(row[7]) else "",
                int(row[8]) if math.isfinite(row[8]) else "",
                int(row[9]) if math.isfinite(row[9]) else "",
            ])
            # csv writer expects one value per header column; repair mapping below
    # Rewrite with correct 10-column mapping explicitly.
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        for row in arr:
            writer.writerow([
                int(row[0]),
                f"{row[1]:.1f}",
                f"{row[2]:.1f}",
                f"{row[3]:.2f}",
                f"{row[4]:.2f}",
                f"{row[5]:.2f}",
                int(row[6]),
                int(row[7]),
                int(row[8]),
                int(row[9]),
            ])


# --------------------------------------------------------------------------- #
# Sweep analysis
# --------------------------------------------------------------------------- #
def split_segments(arr: np.ndarray) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    start = 0
    for i in range(1, len(arr)):
        if arr[i, 1] != arr[i - 1, 1]:
            segments.append((start, i - 1))
            start = i
    segments.append((start, len(arr) - 1))
    return segments


def analyze_sweep(arr: np.ndarray, stable_seconds: float) -> list[dict]:
    t = arr[:, 0] / 1000.0
    rows_out: list[dict] = []
    for a, b in split_segments(arr):
        tt = t[a:b + 1]
        dur = float(tt[-1] - tt[0])
        if dur < max(15.0, stable_seconds + 5.0):
            continue
        if b - a < 10:
            continue
        cutoff = tt[-1] - max(3.0, min(stable_seconds, max(3.0, dur * 0.25)))
        mask = tt >= cutoff
        if mask.sum() < 5:
            mask = np.ones(len(tt), dtype=bool)
        y = arr[a:b + 1, 2]
        d = arr[a:b + 1, 3]
        ff = arr[a:b + 1, 4]
        ii = arr[a:b + 1, 5]
        stable_y = y[mask]
        stable_t = tt[mask]
        target = float(arr[a, 1])
        stable_mean = float(np.mean(stable_y))
        error = stable_mean - target
        error_pct = 100.0 * error / target if abs(target) > 1 else 0.0
        rows_out.append({
            "target_rpm": target,
            "dwell_start_tick": int(arr[a, 0]),
            "dwell_end_tick": int(arr[b, 0]),
            "duration_s": round(dur, 2),
            "stable_samples": int(mask.sum()),
            "stable_rpm_mean": round(stable_mean, 2),
            "stable_rpm_std": round(float(np.std(stable_y)), 2),
            "stable_rpm_min": round(float(np.min(stable_y)), 2),
            "stable_rpm_max": round(float(np.max(stable_y)), 2),
            "duty_mean": round(float(np.mean(d)), 2),
            "ff_mean": round(float(np.mean(ff)), 2),
            "integral_mean": round(float(np.mean(ii)), 3),
            "steady_state_error_rpm": round(error, 2),
            "steady_state_error_pct": round(error_pct, 3),
            "within_5pct": "PASS" if abs(error_pct) <= 5.0 else "FAIL",
        })
    return rows_out


def summarize_sweep_by_target(sweep_rows: list[dict]) -> list[dict]:
    groups: dict[float, list[dict]] = {}
    for row in sweep_rows:
        groups.setdefault(row["target_rpm"], []).append(row)
    out = []
    for target, rows in groups.items():
        err_means = [r["steady_state_error_pct"] for r in rows]
        rpm_means = [r["stable_rpm_mean"] for r in rows]
        duty_means = [r["duty_mean"] for r in rows]
        ripples = [r["stable_rpm_std"] for r in rows]
        out.append({
            "target_rpm": target,
            "num_dwells": len(rows),
            "mean_stable_rpm": round(float(np.mean(rpm_means)), 2),
            "mean_ripple_std": round(float(np.mean(ripples)), 2),
            "mean_duty": round(float(np.mean(duty_means)), 2),
            "mean_steady_state_error_rpm": round(float(np.mean([r["steady_state_error_rpm"] for r in rows])), 2),
            "mean_steady_state_error_pct": round(float(np.mean(err_means)), 3),
            "worst_abs_error_pct": round(float(max(abs(x) for x in err_means)), 3),
            "all_within_5pct": "PASS" if all(abs(x) <= 5.0 for x in err_means) else "FAIL",
        })
    out.sort(key=lambda r: r["target_rpm"])
    return out


# --------------------------------------------------------------------------- #
# Step-response analysis
# --------------------------------------------------------------------------- #
def crossing_time(t: np.ndarray, y: np.ndarray, threshold: float, rising: bool) -> float:
    if rising:
        idx = np.where(y >= threshold)[0]
    else:
        idx = np.where(y <= threshold)[0]
    if len(idx) == 0:
        return float("nan")
    i = int(idx[0])
    if i == 0:
        return float(t[0])
    t0, t1 = float(t[i - 1]), float(t[i])
    y0, y1 = float(y[i - 1]), float(y[i])
    denom = y1 - y0
    if abs(denom) < 1e-9:
        return float(t[i])
    alpha = (threshold - y0) / denom
    alpha = min(1.0, max(0.0, alpha))
    return t0 + alpha * (t1 - t0)


def analyze_step_segments(arr: np.ndarray) -> list[dict]:
    t = arr[:, 0] / 1000.0
    segments = split_segments(arr)
    out: list[dict] = []
    for k in range(1, len(segments)):
        a, b = segments[k]
        pa, _ = segments[k - 1]
        if b - a < 10:
            continue
        prev_target = float(arr[pa, 1])
        target = float(arr[a, 1])
        if abs(target - prev_target) < 1e-6:
            continue
        tt = t[a:b + 1]
        yy = arr[a:b + 1, 2]
        duty = arr[a:b + 1, 3]
        dur = float(tt[-1] - tt[0])
        amp = target - prev_target
        rising = amp > 0
        abs_amp = abs(amp)

        # 10% / 90% rise time
        if rising:
            lo = prev_target + 0.1 * abs_amp
            hi = prev_target + 0.9 * abs_amp
        else:
            lo = prev_target - 0.1 * abs_amp
            hi = prev_target - 0.9 * abs_amp
        t10 = crossing_time(tt, yy, lo, rising)
        t90 = crossing_time(tt, yy, hi, rising)
        rise_time = (t90 - t10) if (math.isfinite(t10) and math.isfinite(t90)) else float("nan")

        # Overshoot
        if rising:
            overshoot = (float(np.max(yy)) - target) / abs_amp * 100.0 if abs_amp > 0 else 0.0
        else:
            overshoot = (target - float(np.min(yy))) / abs_amp * 100.0 if abs_amp > 0 else 0.0

        # Settling time using 5% band around target
        band = 0.05 * abs(target) if abs(target) > 1 else 5.0
        outside = np.abs(yy - target) > band
        if outside.any():
            last_out = int(np.where(outside)[0].max())
            settle = float(tt[last_out + 1]) if last_out + 1 < len(tt) else float("nan")
        else:
            settle = float(tt[0])
        settle_time = settle - float(tt[0]) if math.isfinite(settle) else float("nan")

        # steady-state window: last 5 seconds, or whole short segment if needed
        win = 5.0
        mask = tt >= (tt[-1] - win)
        if mask.sum() < 5:
            mask = np.ones(len(tt), dtype=bool)
        ss_mean = float(np.mean(yy[mask]))
        ss_std = float(np.std(yy[mask]))
        ss_err = ss_mean - target
        ss_err_pct = 100.0 * ss_err / target if abs(target) > 1 else 0.0

        out.append({
            "from_target_rpm": round(prev_target, 1),
            "to_target_rpm": round(target, 1),
            "step_amp_rpm": round(amp, 1),
            "dwell_duration_s": round(dur, 2),
            "rise_time_10_90_s": round(rise_time, 3) if math.isfinite(rise_time) else "",
            "settle_5pct_s": round(settle_time, 3) if math.isfinite(settle_time) else "",
            "overshoot_pct": round(overshoot, 2),
            "steady_state_rpm": round(ss_mean, 2),
            "steady_state_error_rpm": round(ss_err, 2),
            "steady_state_error_pct": round(ss_err_pct, 3),
            "rpm_ripple_std": round(ss_std, 2),
            "max_rpm": round(float(np.max(yy)), 2),
            "min_rpm": round(float(np.min(yy)), 2),
            "duty_mean": round(float(np.mean(duty)), 2),
            "duty_max": round(float(np.max(duty)), 2),
            "samples": int(len(tt)),
        })
    return out


def write_dict_csv(rows: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        # still create an empty file with no data
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("")
        return
    fieldnames = list(rows[0].keys())
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_sweep_summary(summary: list[dict]) -> None:
    print("\n=== SWEEP STEADY-STATE BY TARGET ===")
    print(f"{'target':>8} {'n':>3} {'rpm_ss':>9} {'ripple':>7} {'duty':>7} {'err%':>8} {'spec':>5}")
    for r in summary:
        print(f"{r['target_rpm']:8.1f} {r['num_dwells']:3d} "
              f"{r['mean_stable_rpm']:9.1f} {r['mean_ripple_std']:7.1f} "
              f"{r['mean_duty']:7.2f} {r['mean_steady_state_error_pct']:8.2f} "
              f"{r['all_within_5pct']:>5}")


def print_step_summary(rows: list[dict]) -> None:
    print("\n=== STEP-RESPONSE METRICS ===")
    print(f"{'from':>8} {'to':>8} {'dur':>6} {'Ts5%':>7} {'rise':>7} {'OV%':>7} {'err%':>7} {'rip':>6}")
    for r in rows:
        print(f"{r['from_target_rpm']:8.1f} {r['to_target_rpm']:8.1f} "
              f"{r['dwell_duration_s']:6.1f} {str(r['settle_5pct_s']):>7} "
              f"{str(r['rise_time_10_90_s']):>7} {r['overshoot_pct']:7.1f} "
              f"{r['steady_state_error_pct']:7.2f} {r['rpm_ripple_std']:6.1f}")


def make_plots(arr: np.ndarray, stem: str, plot_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"[plot skipped] matplotlib unavailable: {exc}")
        return
    plot_dir.mkdir(parents=True, exist_ok=True)
    t = arr[:, 0] / 1000.0
    fig, ax = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax[0].plot(t, arr[:, 2], label="actual RPM", linewidth=1)
    ax[0].plot(t, arr[:, 1], label="target RPM", linewidth=1, linestyle="--")
    ax[0].set_ylabel("RPM")
    ax[0].legend()
    ax[0].grid(True, alpha=0.3)
    ax[1].plot(t, arr[:, 3], label="duty %", linewidth=1)
    ax[1].set_ylabel("Duty (%)")
    ax[1].set_xlabel("Time (s)")
    ax[1].grid(True, alpha=0.3)
    fig.tight_layout()
    out = plot_dir / f"{stem}.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"[plot] saved {out}")


def process_one(path: Path, outdir: Path, clean_dir: Path, stable_seconds: float,
                do_plot: bool) -> dict:
    arr, stats = parse_raw_log(path)
    stem = path.stem
    clean_path = clean_dir / f"{stem}.csv"
    write_clean_csv(arr, clean_path)

    sweep_rows = analyze_sweep(arr, stable_seconds)
    sweep_summary = summarize_sweep_by_target(sweep_rows)
    step_rows = analyze_step_segments(arr)

    sweep_detail_path = outdir / f"{stem}_sweep_detail.csv"
    sweep_summary_path = outdir / f"{stem}_sweep_summary.csv"
    step_path = outdir / f"{stem}_step_metrics.csv"
    write_dict_csv(sweep_rows, sweep_detail_path)
    write_dict_csv(sweep_summary, sweep_summary_path)
    write_dict_csv(step_rows, step_path)

    print(f"\n=== {path.name} ===")
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"clean CSV : {clean_path} ({len(arr)} rows)")
    if sweep_summary:
        print_sweep_summary(sweep_summary)
        print(f"sweep detail/summary: {sweep_detail_path}, {sweep_summary_path}")
    if step_rows:
        print_step_summary(step_rows)
        print(f"step metrics: {step_path}")

    if do_plot:
        make_plots(arr, stem, clean_dir / "plots")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze FANPWM MCU RPM logs")
    parser.add_argument("inputs", nargs="*", help="Raw log files. Default: logs/COM4_*.csv")
    parser.add_argument("--outdir", default=str(ROOT / "data" / "output"),
                        help="Output directory for analysis CSVs")
    parser.add_argument("--clean-dir", default=str(ROOT / "logs" / "clean"),
                        help="Output directory for cleaned row-level CSVs")
    parser.add_argument("--stable-seconds", type=float, default=8.0,
                        help="Stable window length (seconds) for sweep steady-state")
    parser.add_argument("--plot", action="store_true", help="Save time-series plots")
    args = parser.parse_args()

    inputs = args.inputs
    if not inputs:
        inputs = sorted(glob.glob(str(ROOT / "logs" / "COM4_*.csv")))
    if not inputs:
        raise SystemExit("No input files found. Pass one or more CSV paths.")

    outdir = Path(args.outdir)
    clean_dir = Path(args.clean_dir)
    for raw in inputs:
        process_one(Path(raw), outdir, clean_dir, args.stable_seconds, args.plot)


if __name__ == "__main__":
    main()