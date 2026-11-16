# -*- coding: utf-8 -*-
"""用 raw data 作 baseline，比較開迴路 duty sweep 與閉迴路追蹤。

輸出：data/output/openloop_vs_closedloop_baseline.png
"""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ---- open-loop baseline：duty sweep ----
ol = pd.read_csv(OUT / "pwm_rpm_wind_relation.csv")
dol = ol["duty_pct"].to_numpy(float)
rol = ol["rpm"].to_numpy(float)

# ---- closed-loop run ----
cl_path = ROOT / "logs" / "clean" / "COM4_2026_11_01.15.35.11.924.csv"
cl = pd.read_csv(cl_path)
# remove transition rows: keep samples whose target stable for at least 5s
t = cl["tick"].to_numpy(float) / 1000.0
target = cl["target_rpm"].to_numpy(float)
actual = cl["actual_rpm"].to_numpy(float)
duty = cl["duty"].to_numpy(float)

fig, axes = plt.subplots(2, 2, figsize=(13, 9))

# 1. open-loop duty -> RPM (baseline characterization)
ax = axes[0, 0]
ax.plot(dol, rol, "o-", color="tab:blue")
ax.set_xlabel("Open-loop PWM duty (%)")
ax.set_ylabel("Steady RPM")
ax.set_title("Open-loop baseline: Duty -> RPM")
ax.grid(True, alpha=0.3)

# 2. closed-loop: actual RPM vs output duty (same x axis as open-loop)
ax = axes[0, 1]
ax.scatter(duty, actual, s=4, alpha=0.15, color="tab:green", label="closed-loop actual")
ax.plot(dol, rol, "o-", color="tab:blue", lw=2, label="open-loop baseline")
ax.set_xlabel("PWM duty (%)")
ax.set_ylabel("RPM")
ax.set_title("Open-loop vs Closed-loop (RPM vs Duty)")
ax.grid(True, alpha=0.3)
ax.legend()

# 3. closed-loop tracking error vs output duty
ax = axes[1, 0]
err = actual - target
ax.scatter(duty, err, s=4, alpha=0.15, color="tab:red")
ax.axhline(0, color="k", lw=1)
ax.set_xlabel("PWM duty (%)")
ax.set_ylabel("RPM error (actual - target)")
ax.set_title("Closed-loop error vs PWM duty")
ax.grid(True, alpha=0.3)

# 4. error distribution by target band (settled, last 20 samples per target)
ax = axes[1, 1]
cl["tgt_round"] = cl["target_rpm"].round(0)
# take tail of each target plateau
groups = []
for tgt, g in cl[cl.target_rpm > 0].groupby("tgt_round"):
    gg = g.tail(20)
    groups.append((tgt, gg["actual_rpm"] - gg["target_rpm"]))
if groups:
    labels = [f"{g[0]:.0f}" for g in groups]
    data = [g[1].to_numpy() for g in groups]
    bp = ax.boxplot(data, tick_labels=labels, showfliers=False)
    ax.axhline(0, color="k", lw=1)
ax.set_xlabel("Target RPM")
ax.set_ylabel("RPM error (actual - target)")
ax.set_title("Closed-loop steady-state error by target")
ax.grid(True, alpha=0.3, axis="y")
ax.tick_params(axis="x", rotation=45)

fig.suptitle("Open-loop baseline vs Closed-loop control", fontsize=14)
fig.tight_layout(rect=[0, 0, 1, 0.96])
os.makedirs(OUT, exist_ok=True)
out_path = OUT / "openloop_vs_closedloop_baseline.png"
fig.savefig(out_path, dpi=150)
print(f"saved: {out_path}")

# metrics
settled = cl[cl.target_rpm > 0].groupby("tgt_round").tail(10)
mae = (settled.actual_rpm - settled.target_rpm).abs().mean()
print(f"settled MAE = {mae:.1f} RPM")
print(f"target range = {cl.target_rpm.min():.0f}..{cl.target_rpm.max():.0f} RPM")
