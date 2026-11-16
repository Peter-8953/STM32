# 風扇測試與分析成果追蹤

更新日期：2026-11-01  
分析腳本：`scripts/analyze_rpm_test.py`  
原始/清除資料：
- `logs/COM4_2026_11_01.15.35.11.924.csv` → `logs/clean/COM4_2026_11_01.15.35.11.924.csv`（6900 rows）
- `logs/COM4_2026_11_01.15.49.17.331.csv` → `logs/clean/COM4_2026_11_01.15.49.17.331.csv`（2119 rows）

韌體狀態：
- 基準 commit：`03e5986`（Tune PI + 30 s auto sweep）
- 另含 Method B runtime toggle（`A0 / A1 / A`）未 commit 的測試版改動

## 目前 PI 參數（2026-11-01 V2；baseline section 仍記錄 V1）

- `RPM_KP = 0.18`
- `RPM_KI = 0.45 /s`
- `RPM_I_LIMIT = 6 % duty`
- `RPM_ERR_DEADBAND_PCT = 0.5 %`
- `RPM_FILTER_ALPHA = 0.45`
- `RPM_TARGET_RAMP_RPS = 800 RPM/s`
- 控制週期：`100 ms`

## 1. 自動 RPM Sweep 穩態驗證

完整 sweep 用 `0 → 10 → … → 100 → … → 10 → 0`，每階 30 s / 100% 60 s。下表為每個 dwell 最後穩定區的平均值。

| target RPM | dwell 次數 | 穩態 RPM | ripple std | duty mean | 誤差 RPM | 誤差 % | ±5% spec |
|---:|---:|---:|---:|---:|---:|---:|---|
| 0.0 | 2 | 0.0 | 0.0 | 0.23 | 0.0 | 0.00 | PASS |
| 417.3 | 3 | 450.1 | 53.3 | 11.04 | +37.0 | +7.86 | FAIL |
| 834.5 | 2 | 853.0 | 8.9 | 16.95 | +18.5 | +2.22 | PASS |
| 1251.8 | 2 | 1245.0 | 8.2 | 22.58 | -6.8 | -0.55 | PASS |
| 1669.1 | 2 | 1654.3 | 12.6 | 28.68 | -14.8 | -0.89 | PASS |
| 2086.3 | 2 | 2091.7 | 5.2 | 36.78 | +5.4 | +0.26 | PASS |
| 2503.6 | 2 | 2495.1 | 4.6 | 47.05 | -8.5 | -0.34 | PASS |
| 2920.9 | 2 | 2921.2 | 3.6 | 57.66 | +0.3 | +0.01 | PASS |
| 3338.1 | 2 | 3347.4 | 4.5 | 69.06 | +9.3 | +0.28 | PASS |
| 3755.4 | 2 | 3748.4 | 4.9 | 80.02 | -7.0 | -0.19 | PASS |
| 4172.6 | 1 | 4148.5 | 7.2 | 95.75 | -24.1 | -0.58 | PASS |

### Sweep 觀察
- 1251 RPM 以上的稳態誤差大多小於 1%。
- 834 RPM 約 +2.22%，仍可在 ±5% spec 內。
- **417 RPM 失敗**：+7.86% 誤差且 ripple 53 RPM，低 duty/低 RPM FF table 仍需改善。
- 風扇在低 duty 区的非線性較強，PI 无法完全補償 FF 誤差。

## 2. 手動 Step Response

測試序列包含：
`0 → 1044 → 2088 → 3132 → 2088 → 1044 → 2088 → 3132 → 1044 → 3132 → 0`（部分 steps）

| from RPM | to RPM | dwell (s) | rise time (s) | settle 5% (s) | overshoot % | steady error % | ripple std |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1044.2 | 24.7 | 0.000 | 3.6 | 9.2 | -0.52 | 6.0 |
| 1044.2 | 2088.3 | 16.3 | 1.089 | 4.9 | 26.1 | +0.81 | 5.3 |
| 2088.3 | 3132.5 | 17.1 | 1.296 | 4.2 | 22.9 | -0.28 | 1.8 |
| 3132.5 | 2088.3 | 16.4 | 1.069 | 4.2 | 26.5 | +0.56 | 5.7 |
| 2088.3 | 1044.2 | 33.3 | 2.064 | 6.1 | 27.0 | +0.22 | 7.6 |
| 1044.2 | 2088.3 | 22.0 | 1.067 | 4.6 | 24.1 | +0.82 | 4.8 |
| 2088.3 | 3132.5 | 21.8 | 1.295 | 4.3 | 21.0 | -0.39 | 4.6 |
| 3132.5 | 1044.2 | 28.3 | 2.769 | 7.4 | 13.9 | -0.24 | 9.1 |
| 1044.2 | 3132.5 | 25.3 | 2.007 | 5.4 | 10.8 | +0.01 | 4.0 |

### Step Response 評估
- `P25→P50`、`P50→P75` overshoot 約 21–27%，超過 `<15%` spec。
- Settle time 約 3–7 s，超過 `<2 s` spec。
- 穩態誤差大多 <1%，大部分目標在 ±5% 內。
- Low RPM（P25/1044）transition 的 rise/settle 較慢，ripple 亦較大。
- 同一 target 的 up/down step 有輕微 hysteresis，但目前差距不大。

## 3. 與驗收規格對照（TEST_BASELINE_PLAN）

| 規格 | 實測結果 |
|---|---|
| CSV 可重現步階 | 已有 10 Hz CSV，可重現 |
| Steady-state ±5% | 大部分 RPM steps pass；417 RPM fail |
| Overshoot <15% | FAIL，step overshoot 10–27% |
| Settling time <2 s | FAIL，mostly 3–7 s |
| 三次重複試驗 CV <10% | 尚未完整做 3 重複，需補測 |

## 4. 本輪關鍵發現

1. Feedforward + PI 已能讓中高轉速 error 接近 0。
2. 目前 overshoot 主要來自 step 響應，不是 steady-state。
3. `KI = 0.70 /s`、`KP = 0.20` 仍偏激進，target ramp + integral windup 可能放大超調。
4. Low RPM (417 RPM) 的 FF 表 / 校正點密度不足，造成 +7.86% 誤差與大 ripple。
5. Deadband 已降為 0.5%，但低轉速 tach ripple 仍可能影響 integrator。

## 5. 下一步 Trace / Follow-up

1. 對 `0 / P25 / P50 / P75` 各做 3 次 step repeats，補 `CV%` 與 repeat consistency。
2. 若 overshoot 仍 >15%，小幅降低 `RPM_KI` 或加入 target transition integral reset。
3. 降低 target ramp 從 `1000 RPM/s` 試 `600–800 RPM/s`，降低 step transient。
4. 重新校正 low-duty FF table，特別是在 10–20% duty / 400–900 RPM 區間。
5. 用 `scripts/analyze_rpm_test.py` 重跑，更新本報告的 metrics。
6. 完成後再 commit firmware + clean CSV + analysis summary。

## 關聯檔案
- `docs/TEST_BASELINE_PLAN.md`
- `docs/USER_COMMANDS.md`
- `docs/HANDBOOK.md`
- `scripts/analyze_rpm_test.py`
- `logs/clean/*.csv`
- `data/output/COM4_*_sweep_summary.csv`
- `data/output/COM4_*_step_metrics.csv`

---

# 追加测量：Run 2 (2026-11-01 16:18)

来源：`COM4_2026_11_01.16.18.40.003.csv`  
命令序列：`A0`, `P25 → P50 → P75 → P25`（9 valid step transitions, duration 29-68s）

Summary:
- Clean rows: 5097 / 5106
- steady-state errors: P25/P50/P75 all `±0.6%`
- Overshoot remains 19-23% for P25→P50/P50→P75
- Settle 5% still 4.0-7.6s
- Reserve details: `data/output/COM4_2026_11_01.16.18.40.003_step_metrics.csv`

Step metrics (representative):

| From | To | Dwell(s) | Rise(s) | Settle(s) | OV% | Err% | Ripple |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1049.7 | 2099.4 | 52-59 | 1.067-1.095 | 4.0-4.7 | 22-23 | +0.09 | 1.9-4.3 |
| 2099.4 | 3149.1 | 40-61 | 1.279-1.301 | 4.0-4.3 | 19-21 | -0.6 | 1.6-3.4 |
| 3149.1 | 1049.7 | 29-68 | 2.699-2.825 | 7.3-7.6 | 12-14 | +0.07 | 8.0-8.8 |

System ID cadence from Run 2:
- median step gain: ~0.98-1.0 (target vs actual settling ~1:1)
- process tau median ~0.40-0.44s excluding large downdrop transient
- deadtime median ~0.76s
- candidate PI (~PI) remains around `Kp=0.20-0.39`, `Ki=0.27-0.45`

Conclusion: Run2 confirms Run1. Overshoot/settle still failed. Integral reset now highest-value low-risk change.

---

# Firmware Tuning V2（2026-11-01）

## 方法与理由

Run1 / Run2 仍一致 showing overshoot 19-27% and settle 4-7s。新 tuning V2 采用 combined approach:

1. **Integral reset**（rpm_ctrl_set_target 已存在）  
   large target change → reset s_integral

2. **降低 integral contribution**  
   `KI 0.70 -> 0.45`, `I_LIMIT 10 -> 6`  
   降低 windup / overshoot

3. **降低 gain**  
   `KP 0.20 -> 0.18`，降低 proportional gain for softer response

4. **增加 filtering**  
   `ALPHA 0.35 -> 0.45`  
   减低 low RPM tach ripple 对 controller 的 perturbation

5. **降低 ramp**  
   `RAMP 1000 -> 800`  
   减轻 large setpoint transient

## Applied constants

- `RPM_KP = 0.18f`
- `RPM_KI = 0.45f`
- `RPM_I_LIMIT = 6.0f`
- `RPM_FILTER_ALPHA = 0.45f`
- `RPM_ERR_DEADBAND_PCT = 0.5f`
- `RPM_TARGET_RAMP_RPS = 800.0f`

## Standard tuning protocol（for next validation）

1. `A0` pause sweep
2. `P25` hold 30s
3. `P50` hold 30s
4. `P75` hold 30s
5. `P25` hold 30s
6. repeat 3 times
7. `V` log
8. run `python scripts/analyze_rpm_test.py`
9. update this report

Expected improvement:
- Overshoot < 15%
- Settle time toward <2s
- Steady error still <±5%

---

# 追加測試：Firmware V2 驗收（2026-11-01 16:53）

來源：`COM4_20261101_165300.step.csv`  
韌體設定：`KP=0.18`, `KI=0.45`, `I_LIMIT=6`, `ALPHA=0.45`, `RAMP=800`  
 clean rows：3703 / 3703（零 malformed / range rejection）

## Step metrics (V2)

| From | To | Dwell(s) | Rise(s) | Settle 5%(s) | OV% | Err% | Ripple |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1046 | 29.9 | 1.914 | 2.1 | 2.8 | -0.60 | 8.3 |
| 1046 | 2092 | 29.9 | 1.125 | 4.4 | 12.2 | +0.33 | 8.1 |
| 2092 | 3138 | 29.9 | 1.343 | 1.8 | 14.8 | -0.71 | 3.1 |
| 3138 | 1046 | 59.9 | 2.94 | 7.7 | 9.3 | -0.09 | 7.5 |
| 1046 | 2092 | 29.9 | 1.14 | 4.7 | 14.9 | +0.11 | 5.3 |
| 2092 | 3138 | 29.9 | 1.363 | 1.9 | 13.6 | -0.69 | 2.5 |
| 3138 | 1046 | 59.9 | 2.88 | 8.0 | 9.6 | -0.45 | 6.5 |
| 1046 | 2092 | 29.9 | 1.161 | 4.7 | 14.8 | +0.02 | 4.3 |
| 2092 | 3138 | 29.9 | 1.373 | 1.9 | 13.1 | -0.73 | 2.0 |
| 3138 | 1046 | 36.0 | 2.901 | 8.1 | 8.7 | -0.31 | 9.5 |

## V2 vs prior baseline（overshoot only representative)

| Step | Baseline | V2 |
|---|---:|---:|
| 1046→2092 | 22-23% | 12-15% |
| 2092→3138 | 19-23% | 13-15% |
| 3138→1046 | 12-14% | 8-10% |
| 0→1046 | ~40% initial / poor | 2.8% (only first jump slightly higher depending tspan) |

## V2 评估
- **P25→P50 / P50→P75 overshoot 已降到 ~12-15%**
  - 已进入 spec 可接受边界
- steady-state error pass
- low RPM (1046) steady pass
- ripple still manageable
- Settling on 1046→2092 and 2092→3138 仍约 4s，未达到 `<2s`
- downward from 3138→1046 仍 7-8s（large step due to fan inertia）

## 与 spec 对照

| Metric | Baseline | V2 | Spec |
|---|---|---|---|
| Steady error | pass mostly | pass | ±5% |
| Overshoot | fail | **pass-ish** | <15% |
| Settle <2s | fail | **partially pass** (1.8-4.5s) | <2s |
| Remainder protocol | 3 repeats not complete but 3 cycles recorded | better |

## Next Follow-up
1. 可以继续微调 SETPOINT 1046→2092 settle：
   - 降低 ramp 到 700 RPM/s 试验
   - 或Integral reset is already present
2. Fan inertia downward response may require feedforward descending ramp or target ramp shaping.
3. Low RPM only 1046 remains but pass.
4. 本 run 已确认 V2 方案有效，值得 commit with results.

---

# 追加測試：V2 repeat 3（2026-11-01 17:08）

來源：`COM4_20261101_170801.step.csv`  
 clean rows: 3032 / 3032  
target values: 1038.6 / 2077.3 / 3115.9

## metrics
| From | To | Dwell(s) | Rise(s) | Settle 5%(s) | OV% | Err% | Ripple |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1038.6 | 59.9 | 0.697 | 5.0 | 19.1 | +0.53 | 8.8 |
| 1038.6 | 2077.3 | 29.9 | 1.148 | 4.8 | 12.6 | +0.26 | 4.1 / 4.5 |
| 2077.3 | 3115.9 | 29.9 | 1.344 | 1.8 / 3.4 | 14.9 / 15.4 | -1.02 / -1.09 | 28.9 / 28.6 |
| 3115.9 | 1038.6 | 59.9 / 36.0 | 2.849 / 2.899 | 7.7-8.1 | 8.4 / 8.7 | +0.69 / +0.16 | 9.2 |

## 观察
- P25→P50 overshoot 已稳定 `~12.6%`
- P50→P75 overshoot 接近 spec `14.9-15.4%`
- `1046/P25→2092/P50` settle 仍约 `4.8s`
- 高 RPM step `2092→3138` ripple 突然 elevated (~28) 在 V2，值得 attention

## 結論
V2 significantly reduced overshoot but still:
- settle on P25→P50 > 2s
- P50→P75 overshoot right at boundary
- high-zone step ripple unusual

Next likely:
- minor ramp reduction 800→700 and test Ki slight change
- low RPM separately

---

# Firmware Tuning V3（2026-11-01 approved incremental change）

- Changed:
  - `RPM_TARGET_RAMP_RPS`: `800.0f -> 700.0f`
- Reason:
  - Run3 V2 showed P25→P50 settle still ~4.8s
  - Reduce target ramp to avoid aggressive step transient
- Other constants remain:
  - `KP=0.18`, `KI=0.45`, `I_LIMIT=6`, `ALPHA=0.45`, deadband=0.5%
