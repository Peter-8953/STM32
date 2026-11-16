# PWM / RPM / 風速關係（FANPWM 量測模型）

資料來源：`data/output/pwm_rpm_wind_relation.csv`（12Start/fan_wind_analysis 產出；
up/down 平均；RPM 為 CAL 測得的 steady-state 轉速）。

## 1. 量測資料（steady state）

| PWM duty (%) | RPM | wind up (m/s) | wind down (m/s) | hysteresis (m/s) |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0.000 | — | — |
| 12 | 509 | 1.187 | 1.223 | -0.036 |
| 20 | 1042 | 2.269 | 2.306 | -0.036 |
| 30 | 1795 | 3.564 | 3.573 | -0.009 |
| 40 | 2221 | 4.362 | 4.324 | +0.038 |
| 50 | 2629 | 5.186 | 5.142 | +0.044 |
| 60 | 3007 | 5.762 | 5.814 | -0.051 |
| 70 | 3378 | 6.431 | 6.386 | +0.045 |
| 80 | 3763 | 7.235 | 7.047 | +0.188 |
| 90 | 4038 | 7.695 | 7.646 | +0.049 |
| 100 | 4309 | 8.162 | — | — |

推估關係：風量以風速 × 固定截面積 0.01039 m²（≈ 11.5 cm 直徑）計算；
對照 `data/output/pwm_airflow_table.csv`。

## 2. 擬合公式

### 2.1 duty → RPM
三階多项式（快速近似；韌體實際使用 PCHIP 校正表反查，monotonic）：

```
RPM = -1.124e-4 * D^3 - 1.901e-1 * D^2 + 6.389e1 * D - 8.273e1
R^2 = 0.99718
```

低 duty（12–30%）斜率 steepest（42–75 RPM/%），是啟動/低速控制最難的區段。

### 2.2 RPM → 風速（推荐公式）

```
v (m/s) = 1.8527e-3 * RPM + 0.2080
R^2 = 0.99885     RMSE ≈ 0.087 m/s
```

風速與 RPM 幾乎線性（平均增量 ≈ 0.00189 m/s / RPM），可直接用 `target_rpm`
 estimated airspeed。

### 2.3 duty → 風速（無 RPM 回授時）

```
v (m/s) = -4.370e-4 * D^2 + 1.248e-1 * D - 2.929e-2
R^2 = 0.99791
```

單調 PCHIP 補間亦可用（`data/output/pwm_rpm_wind_model.csv` 的 `wind_model_pchip_mps`）。
### 2.4 组合關係（PWM → RPM → 風速）

```
D -> R (PCHIP/cal_rpm[] in firmware) -> v (linear RPM model)
```

或合成

```
v(D) ≈ 0.001853 * RPM(D) + 0.208
```

## 3. 迟滞與重複性

- 上升/下降風速差最大 0.1875 m/s（80% duty），其餘多 < 0.06 m/s。
- 平均绝对迟滞 ≈ 0.055 m/s，約量測的 0.7–1.0%。
- 控制時可忽略方向迟滞，但風速設定點容差建議 ≥ 0.2 m/s.

## 4. 檔案

- 量測表：`data/output/pwm_rpm_wind_relation.csv`
- 擬合模型：`data/output/pwm_rpm_wind_model.csv`
- 擬合摘要：`data/output/pwm_rpm_wind_fit_summary.csv`
- 韌體校正：`rpm_ctrl` on-device calibration table（`cal_rpm[]`），再由
  `PchipInterpolator` / firmware inverse lookup 得 duty = f(target RPM)。
