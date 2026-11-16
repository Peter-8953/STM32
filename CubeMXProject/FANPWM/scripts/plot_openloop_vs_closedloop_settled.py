# -*- coding: utf-8 -*-
"""用 settled 資料比較開/閉迴路，避免 transient noise 讓圖看起來奇怪。"""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# open-loop baseline
ol = pd.read_csv(OUT / "pwm_rpm_wind_relation.csv")
dol = ol["duty_pct"].to_numpy(float)
rol = ol["rpm"].to_numpy(float)

# closed-loop raw -> take tail of each target plateau
cl = pd.read_csv(ROOT / "logs" / "clean" / "COM4_2026_11_01.15.35.11.924.csv")
rows = []
for tgt, g in cl[cl.target_rpm > 0].groupby(cl.target_rpm.round()):
    tail = g.tail(20)
    rows.append({
        "target": tail.target_rpm.mean(),
        "actual": tail.actual_rpm.mean(),
        "duty": tail.duty.mean(),
        "std": tail.actual_rpm.std(),
        "n": len(tail),
    })
settled = pd.DataFrame(rows).sort_values("duty").reset_index(drop=True)

fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
ax = axes[0]
ax.plot(dol, rol, "o-", color="tab:blue", label="open-loop baseline")
ax.errorbar(settled["duty"], settled["actual"], yerr=settled["std"], fmt="s-", color="tab:green",
            capsize=3, label="closed-loop settled mean ± σ")
ax.set_xlabel("PWM duty (%)")
ax.set_ylabel("RPM")
ax.set_title("Open-loop vs Closed-loop (settled points)")
ax.grid(True, alpha=0.3)
ax.legend()

ax = axes[1]
ax.errorbar(settled["duty"], settled["actual"] - settled["target"], yerr=settled["std"],
            fmt="o-", color="tab:red", capsize=3)
ax.axhline(0, color="k", lw=1)
ax.set_xlabel("PWM duty (%)")
ax.set_ylabel("RPM error (actual - target)")
ax.set_title("Closed-loop settled error vs duty")
ax.grid(True, alpha=0.3)

fig.tight_layout()
os.makedirs(OUT, exist_ok=True)
out_path = OUT / "openloop_vs_closedloop_settled.png"
fig.savefig(out_path, dpi=150)
print(f"saved: {out_path}")
print(settled.to_string(index=False, float_format="{:.2f}".format))
