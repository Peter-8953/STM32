#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
System-identification helper for the FANPWM speed loop.

It extracts target-RPM steps from MCU logs, fits a first-order-plus-deadtime
(FOPTD) model to the actual RPM response, and proposes a handful of PI tuning
candidates using direct-synthesis / IMC style formulas.

Usage:
  python scripts/estimate_pi_from_steps.py logs/clean/COM4_*.csv
  python scripts/estimate_pi_from_steps.py logs/COM4_*.csv --min-step-rpm 300

Outputs:
  - Console table with identified tau/theta gain and suggested PI candidates.
  - `data/output/COM4_*_pi_model.csv` with raw fitted values per step.
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import os
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit

ROOT = Path(__file__).resolve().parents[1]


def load_rows(path: Path) -> np.ndarray:
    rows = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        first = fh.readline()
        fh.seek(0)
        has_header = ("target_rpm" in first)
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            cols = s.split(",")
            # Accept either the raw 10-column format or extra trailing commas.
            if len(cols) < 10:
                continue
            try:
                vals = [float(x) for x in cols[:10]]
            except ValueError:
                continue
            rows.append(vals)
    arr = np.asarray(rows, dtype=float)
    if arr.size == 0:
        raise ValueError(f"No rows in {path}")
    arr = arr[np.argsort(arr[:, 0])]
    return arr


def split_segments(arr: np.ndarray) -> list[tuple[int, int]]:
    starts = [0]
    for i in range(1, len(arr)):
        if arr[i, 1] != arr[i - 1, 1]:
            starts.append(i)
    out = []
    for k, a in enumerate(starts):
        b = starts[k + 1] - 1 if k + 1 < len(starts) else len(arr) - 1
        out.append((a, b))
    return out


def foptd_response(t: np.ndarray, amp: float, tau: float, theta: float) -> np.ndarray:
    delay = np.maximum(t - theta, 0.0)
    return 1.0 - np.exp(-delay / max(tau, 1e-3))


def fit_step(t: np.ndarray, y: np.ndarray) -> dict | None:
    if len(t) < 20:
        return None
    t_rel = t - t[0]
    y0 = float(np.mean(y[: min(5, len(y))]))
    y_end = float(np.mean(y[-min(5, len(y)):]))
    amp = float(y_end - y0)
    if abs(amp) < 1e-6:
        return None
    s = (y - y0) / amp
    maxt = float(t_rel[-1])

    def model(t_arr: np.ndarray, tau: float, theta: float) -> np.ndarray:
        return foptd_response(t_arr, amp, tau, theta)

    try:
        popt, _ = curve_fit(
            model,
            t_rel,
            s,
            p0=(max(1.0, maxt / 5.0), min(2.0, maxt / 10.0)),
            bounds=((0.1, 0.0), (maxt, maxt / 2.0)),
            maxfev=2000,
        )
    except Exception:
        return None

    tau, theta = float(popt[0]), float(popt[1])
    # residual std
    pred = model(t_rel, tau, theta)
    resid = float(np.sqrt(np.mean((pred - s) ** 2)))
    # 90% response estimate
    dt = float(t_rel[-1] - t_rel[0])
    t90 = float(t_rel[0])
    for i in range(len(s)):
        if abs(s[i]) >= 0.9:
            t90 = float(t_rel[i])
            break
    return {
        "y0": y0,
        "y_end": y_end,
        "amp": amp,
        "tau": tau,
        "theta": theta,
        "residual": resid,
        "t_span": dt,
        "t90": t90,
    }


def suggested_pi(tau: float, theta: float) -> list[dict]:
    """
    Produce a few candidate PI sets from an IMC / direct-synthesis mindset.
    Tau/theta here come from the target->actual step response, so these are
    *starting points* for loop tuning rather than a final controller design.
    """
    lambda_slow = max(theta * 2.0, tau * 0.25, 0.5)
    lambda_mid = max(theta * 1.0, tau * 0.15, 0.25)
    out = []
    for name, lam in (("conservative", lambda_slow), ("balanced", lambda_mid)):
        lam = max(lam, 1e-3)
        # Standard simplified IMC PI-ish candidate from FOPTD parameters.
        K = 1.0
        Kp = tau / (K * (lam + theta / 2.0))
        Ki = Kp / (tau + theta / 2.0)
        out.append({
            "name": name,
            "lambda_s": round(float(lam), 3),
            "Kp": round(float(Kp), 3),
            "Ki": round(float(Ki), 3),
            "I_limit_suggested": round(float(min(10.0, max(4.0, Kp * 2.5))), 2),
            "ramp_suggested_rpm_s": round(float(max(300.0, tau * 60.0)), 1),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Identify FANPWM speed-loop dynamics from step logs")
    parser.add_argument("inputs", nargs="*", help="Raw or clean CSV logs")
    parser.add_argument("--min-step-rpm", type=float, default=300.0,
                        help="Ignore target transitions smaller than this amplitude")
    parser.add_argument("--outdir", default=str(ROOT / "data" / "output"))
    args = parser.parse_args()

    inputs = args.inputs or sorted(glob.glob(str(ROOT / "logs" / "COM4_*.csv")))
    if not inputs:
        raise SystemExit("No input logs found.")

    all_rows = []
    for raw in inputs:
        p = Path(raw)
        arr = load_rows(p)
        for a, b in split_segments(arr):
            if b - a < 20:
                continue
            t = arr[a:b + 1, 0] / 1000.0
            y = arr[a:b + 1, 2]
            target = float(arr[b, 1])
            prev_target = float(arr[a - 1, 1]) if a > 0 else float(arr[a, 1])
            amp = target - prev_target
            if abs(amp) < args.min_step_rpm:
                continue
            fit = fit_step(t, y)
            if fit is None:
                continue
            fit.update({
                "file": p.name,
                "from_target": prev_target,
                "to_target": target,
                "amp": amp,
                "duration_s": round(float(t[-1] - t[0]), 2),
            })
            all_rows.append(fit)
            candidates = suggested_pi(fit["tau"], fit["theta"])
            print(f"\n[{p.name}] {prev_target:7.1f} -> {target:7.1f} RPM  amp={amp:6.1f}")
            print(f"  identified: tau={fit['tau']:6.2f}s  theta={fit['theta']:5.2f}s  "
                  f"fit_err={fit['residual']:.4f}  t90={fit['t90']:5.2f}s")
            print("  candidate PI (from IMC-style direct synthesis):")
            for c in candidates:
                print(f"    {c['name']:13s}: Kp={c['Kp']:6.3f}  Ki={c['Ki']:6.3f}  "
                      f"I_limit={c['I_limit_suggested']:5.2f}  ramp={c['ramp_suggested_rpm_s']:6.1f}")

    if not all_rows:
        raise SystemExit("No usable step responses found.")

    taus = [r["tau"] for r in all_rows]
    thetas = [r["theta"] for r in all_rows]
    print("\n=== AGGREGATED MODEL (median) ===")
    print(f"  n_steps       : {len(all_rows)}")
    print(f"  tau median    : {np.median(taus):6.3f} s  (min={min(taus):.3f}, max={max(taus):.3f})")
    print(f"  theta median  : {np.median(thetas):6.3f} s  (min={min(thetas):.3f}, max={max(thetas):.3f})")
    mean_tau = float(np.median(taus))
    mean_theta = float(np.median(thetas))
    print("\n  Global starting suggestions:")
    for c in suggested_pi(mean_tau, mean_theta):
        print(f"    {c['name']:13s}: Kp={c['Kp']:6.3f}  Ki={c['Ki']:6.3f}  "
              f"I_limit={c['I_limit_suggested']:5.2f}  ramp={c['ramp_suggested_rpm_s']:6.1f}")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    # One model CSV per input stem (append aggregates only once at end).
    rows_out = []
    for r in all_rows:
        rows_out.append({
            "file": r["file"],
            "from_target_rpm": r["from_target"],
            "to_target_rpm": r["to_target"],
            "step_amp_rpm": round(r["amp"], 3),
            "duration_s": r["duration_s"],
            "tau_s": round(r["tau"], 4),
            "theta_s": round(r["theta"], 4),
            "fit_residual": round(r["residual"], 5),
            "t90_s": round(r["t90"], 3),
        })
    outpath = outdir / "pi_sysid_candidates.csv"
    with outpath.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"\n[output] {outpath}  ({len(rows_out)} fitted steps)")

    print("\nRecommended workflow:")
    print("  1. Re-run after collecting duty-step (open-loop) data if available.")
    print("  2. Use candidates above as starting offsets, then hardware-validate only 2-3.")
    print("  3. Add integral reset at target changes before judging Ki.")


if __name__ == "__main__":
    main()