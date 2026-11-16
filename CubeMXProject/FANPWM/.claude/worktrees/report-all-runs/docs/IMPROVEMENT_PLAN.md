# FANPWM PID Tuning & Workflow Improvement Plan
（基於 `ALL_RUNS_SUMMARY_REPORT.md` 與所有 runs 分析）

## 執行原則
1. **一次只改一件事**，每次改動都跑 **3-repeat clean protocol**。
2. **Baseline = V2**：KP 0.18 / KI 0.45 / I_LIMIT 6 / ALPHA 0.45 / RAMP 800。
3. **Acceptance Gate**：
   - 穩態誤差 < ±5%
   - 超調 < 15%
   - Settle < 2 s
   - Ripple < 10
   - 3-repeat CV < 10%

---

## Phase 0 — Baseline Freeze
- [ ] commit 當前 firmware + reports（branch: `main` or `tuning-v2-baseline`）
- [ ] 跑 1 run 完整 protocol（A0, V ON, P25/P50/P75/P25 ×3, hold 30s）
- [ ] 產出 clean + sweep + step metrics，歸檔 run id

## Phase 1 — Instrumentation (observability)
- [ ] log `deadband_hit`, `integral_clamped`, `ff_clamped` events
- [ ] log `setpoint_ramp_value` 與 transition slope
- [ ] log transition start/end ticks（target change）
- [ ] 確認 reverse-PI residual 仍 <0.1%

## Phase 2 — Low RPM Feedforward Calibration
- [ ] 針對 P10/P15/P20 做 targeted step test（0→目標→hold）
- [ ] 用 `fit_ff.py` 重算低 duty 區間 FF 表
- [ ] 驗收：417 RPM steady-state err < ±5%，ripple < 15
- [ ] run 3-repeat，記錄 before/after

## Phase 3 — Integral Conditioning
- [ ] deadband 門檻測試（0.5% vs 1.0%）
- [ ] conditional integration：僅當 |err| > deadband 時累積
- [ ] anti-windup：duty 飽和時 freeze integral
- [ ] I_LIMIT 掃描：6 → 4 → 8（單因素實驗）
- [ ] 每項單獨跑 3-repeat，比較 overshoot/settle

## Phase 4 — PI Candidate Experiments
- [ ] 從 FOPTD sysID（tau≈0.43s, θ≈0.76s）挑 candidate
  - balanced: KP≈0.374, KI≈0.463
  - conservative: KP≈0.225, KI≈0.278
- [ ] 用 3-repeat protocol 比較 gate 達成度
- [ ] 不直接灌入 constants，保留 version control

## Phase 5 — Ramp / Transition Shaping
- [ ] ramp rate 實驗：800 vs 700 vs 600（已驗 800→700 無改善，試 600）
- [ ] downward step 專門處理（重置 I、boost FF、slower descent）
- [ ] 測量 rise 10-90 → 90% / settle reopen time

## Phase 6 — Standardized Acceptance
- [ ] 每次 run 自動產出：
  - clean CSV
  - sweep summary
  - step metrics
  - run manifest（firmware sha、git commit、params）
- [ ] 全 suite median/CV 計算
- [ ] gate fail → 回退上一項，更新 `TEST_RESULTS.md`

## Decision Log
- **Keep baseline**：V2 目前是 steady-tracking 最穩， overshoot 仍需改善
- **Low RPM fail**（417 RPM）優先修 FF，非 PI
- **Integral saturation（6.0）** 與下衝振盪高度相關
- **Ramp 800→700** 已驗證 settle 無改善、overshoot 略差，僅作參考

## References
- `PROJECT_SUMMARY.md` §8 測試結果
- `PI_TUNING_STRATEGY.md`
- `TEST_BASELINE_PLAN.md`
- `ALL_RUNS_SUMMARY_REPORT.md`