# -*- coding: utf-8 -*-
"""畫出 PWM / RPM / 風速 關係圖。

執行：
    python scripts/plot_pwm_rpm_wind.py
輸出：
    data/output/pwm_rpm_wind_relation.png
"""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

SRC = OUT / "pwm_rpm_wind_relation.csv"
df = pd.read_csv(SRC)
d = df["duty_pct"].to_numpy(float)
r = df["rpm"].to_numpy(float)
wu = df["wind_up_mps"].to_numpy(float)
wd = df["wind_down_mps"].to_numpy(float)
w = np.array([np.nanmean([wu[i], wd[i]]) for i in range(len(df))])

# fit models
coef_r = np.polyfit(d, r, 3)
coef_vr = np.polyfit(r, w, 1)
coef_vd = np.polyfit(d, w, 2)

fig, axes = plt.subplots(2, 2, figsize=(12, 9))

# 1. duty vs RPM
ax = axes[0, 0]
ax.plot(d, r, "o-", label="measured (CAL)")
dd = np.linspace(d.min(), d.max(), 200)
ax.plot(dd, np.polyval(coef_r, dd), "--", label="poly3 fit")
ax.set_xlabel("PWM duty (%)")
ax.set_ylabel("RPM")
ax.set_title("Duty vs RPM")
ax.grid(True, alpha=0.3)
ax.legend()

# 2. RPM vs wind (recommended linear)
ax = axes[0, 1]
ax.plot(r, w, "o", label="measured (up/down avg)")
rr = np.linspace(r.min(), r.max(), 200)
ax.plot(rr, np.polyval(coef_vr, rr), "-", label=f"linear: v={coef_vr[0]:.4g}*RPM+{coef_vr[1]:.3g}")
ax.set_xlabel("RPM")
ax.set_ylabel("Wind speed (m/s)")
ax.set_title("RPM vs Wind Speed")
ax.grid(True, alpha=0.3)
ax.legend()

# 3. duty vs wind with hysteresis
ax = axes[1, 0]
ax.plot(d, wu, "o-", label="wind up")
ax.plot(d, wd, "s--", label="wind down")
ax.plot(d, np.polyval(coef_vd, d), "-", label="poly2 fit (avg)")
ax.set_xlabel("PWM duty (%)")
ax.set_ylabel("Wind speed (m/s)")
ax.set_title("Duty vs Wind Speed (hysteresis)")
ax.grid(True, alpha=0.3)
ax.legend()

# 4. hysteresis magnitude
ax = axes[1, 1]
h = wu - wd
ax.bar(d[~np.isnan(h)], np.abs(h[~np.isnan(h)]), width=4, color="tab:orange", alpha=0.7)
ax.axhline(0.1875, color="r", linestyle="--", label="max 0.1875 m/s")
ax.set_xlabel("PWM duty (%)")
ax.set_ylabel("|up - down| (m/s)")
ax.set_title("Hysteresis magnitude")
ax.grid(True, alpha=0.3, axis="y")
ax.legend()

fig.suptitle("PWM / RPM / Wind Speed Relationship", fontsize=14)
fig.tight_layout(rect=[0, 0, 1, 0.96])
os.makedirs(OUT, exist_ok=True)
out_path = OUT / "pwm_rpm_wind_relation.png"
fig.savefig(out_path, dpi=150)
print(f"saved: {out_path}")
plt.show()
