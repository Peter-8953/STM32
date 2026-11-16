# -*- coding: utf-8 -*-
"""
建立 PWM duty (%) / RPM / 風速 (m/s) 的量化關係。

輸入: data/output/pwm_rpm_wind_relation.csv
輸出:
  data/output/pwm_rpm_wind_model.csv         (量測值 + 模型值 + 殘差)
  data/output/pwm_rpm_wind_fit_summary.csv   (各拟合模型係數與 R^2)
"""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

SRC = OUT / "pwm_rpm_wind_relation.csv"
df = pd.read_csv(SRC)
d = df["duty_pct"].to_numpy(dtype=float)
r = df["rpm"].to_numpy(dtype=float)
# up/down 平均風速（任一缺值時取可用值）
w = np.array([np.nanmean([df.loc[i, "wind_up_mps"], df.loc[i, "wind_down_mps"]])
              for i in range(len(df))], dtype=float)
# 風速迟滞 (up - down)
hyst = (df["wind_up_mps"] - df["wind_down_mps"]).to_numpy(dtype=float)

# 1) duty -> RPM：三階多项式（可作快速近似；韌體實際用 PCHIP 校正表反查）
coef_r3 = np.polyfit(d, r, 3)
r_model_poly3 = np.polyval(coef_r3, d)
r2_r3 = 1 - ((r - r_model_poly3) ** 2).sum() / ((r - r.mean()) ** 2).sum()

# 2) duty -> RPM：单调 PCHIP（推荐；與韌體 feedforward 一致精神）
pchip_r = PchipInterpolator(d, r)
r_model_pchip = pchip_r(d)

# 3) RPM -> 風速：線性（量測點 R^2 最高、最可解释）
coef_vr1 = np.polyfit(r, w, 1)
v_model_from_rpm = np.polyval(coef_vr1, r)
r2_vr1 = 1 - ((w - v_model_from_rpm) ** 2).sum() / ((w - w.mean()) ** 2).sum()

# 4) duty -> 風速：二階多项式（給只有 duty、不量 RPM 時用）
coef_vd2 = np.polyfit(d, w, 2)
v_model_from_duty = np.polyval(coef_vd2, d)
r2_vd2 = 1 - ((w - v_model_from_duty) ** 2).sum() / ((w - w.mean()) ** 2).sum()

# 5) duty -> 風速： monotonic PCHIP
pchip_v = PchipInterpolator(d, w)
v_model_pchip = pchip_v(d)

# Residuals
out = pd.DataFrame({
    "duty_pct": d,
    "rpm_measured": r,
    "wind_measured_mps": w,
    "wind_up_mps": df["wind_up_mps"].to_numpy(),
    "wind_down_mps": df["wind_down_mps"].to_numpy(),
    "hysteresis_mps": hyst,
    "rpm_model_poly3": r_model_poly3,
    "rpm_model_pchip": r_model_pchip,
    "wind_model_from_rpm_linear_mps": v_model_from_rpm,
    "wind_model_from_duty_poly2_mps": v_model_from_duty,
    "wind_model_pchip_mps": v_model_pchip,
    "resid_wind_linear_mps": w - v_model_from_rpm,
    "resid_wind_poly2_mps": w - v_model_from_duty,
})
os.makedirs(OUT, exist_ok=True)
out.to_csv(OUT / "pwm_rpm_wind_model.csv", index=False)

summary = pd.DataFrame([
    {"relation": "RPM = f(duty) poly3", "x": "duty_pct", "y": "rpm", "degree": 3,
     "coeffs_high_to_low": ",".join(f"{c:.10g}" for c in coef_r3), "R2": r2_r3},
    {"relation": "wind = a*RPM + b (recommended)", "x": "rpm", "y": "wind_mps", "degree": 1,
     "coeffs_high_to_low": ",".join(f"{c:.10g}" for c in coef_vr1), "R2": r2_vr1},
    {"relation": "wind = a*duty^2 + b*duty + c", "x": "duty_pct", "y": "wind_mps", "degree": 2,
     "coeffs_high_to_low": ",".join(f"{c:.10g}" for c in coef_vd2), "R2": r2_vd2},
])
summary.to_csv(OUT / "pwm_rpm_wind_fit_summary.csv", index=False)

# human-readable console
print("===== PWM / RPM / 風速 關係拟合 =====")
print(f"RPM(duty) poly3: R^2 = {r2_r3:.6f}")
print(f"  RPM = {coef_r3[0]:.6e}*D^3 + {coef_r3[1]:.6e}*D^2 + {coef_r3[2]:.6f}*D + {coef_r3[3]:.6f}")
print(f"wind(RPM) linear (recommended): R^2 = {r2_vr1:.6f}")
print(f"  v = {coef_vr1[0]:.6e}*RPM + {coef_vr1[1]:.6f}   (m/s)")
print(f"wind(duty) poly2: R^2 = {r2_vd2:.6f}")
print(f"  v = {coef_vd2[0]:.6e}*D^2 + {coef_vd2[1]:.6f}*D + {coef_vd2[2]:.6f}   (m/s)")
print(f"迟滞 |up-down| max = {np.nanmax(np.abs(hyst)):.4f} m/s; mean = {np.nanmean(np.abs(hyst)):.4f} m/s")
print(f"RPM/wind 平均增量 = {np.mean(np.diff(w)/np.diff(r)):.6f} m/s per RPM")
print(f"\n輸出：{OUT}")
print("  pwm_rpm_wind_model.csv")
print("  pwm_rpm_wind_fit_summary.csv")
