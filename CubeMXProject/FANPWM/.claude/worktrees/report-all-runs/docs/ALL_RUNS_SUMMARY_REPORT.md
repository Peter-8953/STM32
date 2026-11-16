# FANPWM 所有 Test Runs 總結報告
（由 `logs/` + `data/output/` 各 run 的 sweep/step 分析彙整）

## 1. 資料集範圍
- Raw logs: 8 個 COM4 serial captures（時間 2026-10-30 ~ 2026-11-01）
- 分析輸出: 7 個 `*_sweep_summary.csv` + `*_step_metrics.csv`
  - `COM4_20261101_164437`: raw/empty 分析（無有效 rows）
  - `165300` / `170801` / `171814`: 中 RPM step sweep (~1040/2090/3130)
  - `15.35` / `15.49` / `16.18`: 全轉速 sweep（417 → 4173 RPM）+ step / step protocol
  - `15.4437`: 無有效 summary（檔案未含 CSV rows）

## 2. 穩態 (Sweep) 總結
### 2.1 高 / 中 RPM（1040 ~ 3149 RPM）— 多 run 重複
| Run | target (RPM) | mean stable (RPM) | mean duty (%) | mean err (%) | worst err (%) | ripple (std) | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| 165300 | ~1046 | 1041.17 | 19.92 | -0.471 | 0.614 | 7.47 | PASS |
| 165300 | ~2092 | 2095.46 | 37.16 | +0.161 | 0.167 | 6.44 | PASS |
| 165300 | ~3138 | 3115.84 | 64.30 | -0.713 | 0.720 | 2.79 | PASS |
| 170801 | 1038.6 | 1043.07 | 20.02 | +0.431 | 0.557 | 8.21 | PASS |
| 170801 | 2077.3 | 2084.23 | 37.05 | +0.334 | 0.363 | 3.84 | PASS |
| 170801 | 3115.9 | 3086.91 | 64.08 | -0.930 | 0.952 | 24.37 | PASS |
| 171814 | 1036.7 | 1038.51 | 20.00 | +0.174 | 0.622 | 8.94 | PASS |
| 171814 | 2073.4 | 2070.91 | 36.84 | -0.120 | 0.168 | 3.73 | PASS |
| 171814 | 3110.1 | 3086.34 | 62.04 | -0.764 | 0.910 | 10.23 | PASS |
| 15.49 | 1044.2 | 1040.60 | 19.07 | -0.345 | 0.475 | 7.34 | PASS |
| 15.49 | 2088.3 | 2103.21 | 37.27 | +0.714 | 0.830 | 5.51 | PASS |
| 15.49 | 3132.5 | 3124.85 | 64.41 | -0.244 | 0.405 | 3.88 | PASS |
| 16.18 | 1049.7 | 1046.49 | 19.70 | -0.305 | 0.478 | 7.65 | PASS |
| 16.18 | 2099.4 | 2100.63 | 37.05 | +0.058 | 0.093 | 3.40 | PASS |
| 16.18 | 3149.1 | 3130.28 | 64.48 | -0.598 | 0.605 | 2.74 | PASS |

> 結論：中/高 RPM 穩態全部 PASS，平均誤差通常 -1% ~ +0.8%，最差 <1%；duty 線性上升，ripple 通常 <10（3110/3150 段偏高 ~10–24）。

### 2.2 低 RPM / 全轉速 sweeps（15.35 run）
| target (RPM) | mean stable (RPM) | err (%) | ripple (std) | verdict |
|---:|---:|---:|---:|---|
| 0 | 0.0 | 0.000 | 0.0 | PASS |
| 417.3 | 450.09 | +7.857 | 53.34 | **FAIL** |
| 834.5 | 853.03 | +2.220 | 8.87 | PASS |
| 1251.8 | 1244.97 | -0.546 | 8.21 | PASS |
| 1669.1 | 1654.26 | -0.888 | 12.62 | PASS |
| 2086.3 | 2091.68 | +0.258 | 5.23 | PASS |
| 2503.6 | 2495.11 | -0.339 | 4.60 | PASS |
| 2920.9 | 2921.15 | +0.009 | 3.56 | PASS |
| 3338.1 | 3347.40 | +0.278 | 4.55 | PASS |
| 3755.4 | 3748.36 | -0.188 | 4.86 | PASS |
| 4172.6 | 4148.49 | -0.578 | 7.17 | PASS |

> 結論：**唯一致 System fail 在 ~417 RPM**（+7.9%、ripple 53），其餘中高 RPM 完全 PASS；低轉速 feedforward / tach 量測仍需強化。

## 3. 階躍響應 (Step Response) 總結
### 3.1 典型 upward steps
| transition | rise 10→90 (s) | settle ±5% (s) | overshoot (%) | ripple (std) | err (%) |
|---|---:|---:|---:|---:|---:|
| 0 → ~1040 | 0.70–0.78 | 3.6–6.1 | 9.2–40.8 | 5–8 | -0.5 ~ +0.5 |
| ~1040 → ~2090 | 1.07–1.19 | 4.1–4.9 | 12.1–26.1 | 2–8 | -0.2 ~ +0.8 |
| ~2090 → ~3130 | 1.28–1.37 | 3.4–4.3 | 14.9–22.3 | 2–30 | -0.6 ~ +0.7 |
| 0 → ~3110 (single) | 0.0– (起轉) | 5.2 | 37.3 | 2.55 | -0.66 |
| 0 → 417 (low) | 0.78 | 29.8 (fail) | 65–72 | 53–57 | +8 ~ +9 |

### 3.2 Downward steps
| transition | rise (s) | settle ±5% (s) | overshoot (%) | ripple (std) |
|---|---:|---:|---:|---:|
| ~3130 → ~1040 | 2.69–2.98 | 7.3–8.1 | 8.7–13.9 | 6–10 |
| ~2090 → ~1040 | 2.0–2.2 | 6.1 | ~27 | 7–9 |
| ~1040/2090 → 0 | 2.8 | ~4.5 | ~0/50 (partial) | N/A |

> 結論：**upward settle 大多 3–6 s、overshoot 12–26%**，距離 spec <2 s、<15% 還有差距；**down step 停車更慢（7–8 s）且有大幅下衝**；0→417 run 有 severe overshoot (65–72%) 與超長 settle。

## 4. 控制器行為觀察（來自 deep analysis）
- PI 實現與 duty = ff + Kp·err + I 一致（residual ~0.013%）
- PWM mapping consistent（ccr vs duty*per/100 差 0.8 count）
- **setpoint 非階躍**：反推斜率 ~494 rpm/s（firmware ramp 800→700 後的實際效果），解释 rise fast but settle slow
- **integral 曾飽和至 6.0 (I_LIMIT)**，起轉時 duty 從 0 拉起，末段 duty 主由 ff 支撐（~63.4% @3110）
- deadband/conditional integration 可能造成 integral 跳板式更新（81808, 82808, 87708），與下衝振盪相關

## 5. 總體結論
1. **穩態 tracking**：PASS across 1040–4173 RPM（除 417 RPM）
2. **動態 step**：overshoot 10–30%、settle 3–8 s，**未達 spec**（<15% / <2 s）
3. **下階步與低轉速**：最弱，下衝超 100%、settle 7–8+ s、417 RPM err +7.9% / ripple 53
4. **根因 candidates**：setpoint ramp 行為、integral clamp/deadband gating、low-duty feedforward 不足、tach 量測漣波

## 6. 建議下一步
- 低轉速 P10/P15/P20 targeted step test + feedforward table calibration
- 實驗 integral gating/anti-windup（log conditional updates）
- 以 3-repeat clean protocol 取 median 的 step overshoot/settle
- 比較 upward vs downward transition 分別調節
- V2 baseline (KP 0.18 / KI 0.45 / I 6 / alpha 0.45 / ramp 800) 維持，ramp 微調 800→700 已驗證 settle 無改善、overshoot 略差，若要調 Ki 0.45→0.40 僅在必要時
- 所有改動前保持 clean baseline 數據可追溯

## 7. 參考輸出檔案
- `data/output/*_sweep_summary.csv`
- `data/output/*_step_metrics.csv`
- `data/output/*_sweep_detail.csv`
- `logs/clean/*.csv`
- `docs/TEST_RESULTS.md`, `docs/PI_TUNING_STRATEGY.md`, `docs/PROJECT_SUMMARY.md`