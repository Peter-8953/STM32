# PI Tuning Strategy（FANPWM）

本檔案記錄 2026-11-01 討論/測試後的 PI 整定方案，避免後續反覆窮舉。

## 現況

- 中高 RPM 穩態 error 多數 <1%
- Step overshoot 10-27%（spec <15%）
- Settle time 3-7s（spec <2s）
- Low RPM (417) fail：+7.86% error, ripple 53 RPM

## 方案 1：系統鑑別 + model-based tuning（目前已實作第一部分）

- 腳本：`scripts/estimate_pi_from_steps.py`
- 從 step response 擬合 `FOPTD` (`K, τ, θ`)
- 用 IMC / direct synthesis 給出 `KP / KI` starting candidates
- 已完成：
  - log parsing
  - FOPTD fit per step
  - CSV output: `data/output/pi_sysid_candidates.csv`
- 限制：
  - 這是 closed-loop step response 鑑別，不是 pure open-loop plant
  - duty-step data 可進一步提高 accuracy

## 方案 2：Relay Feedback Auto-tune

- 施加 `X`/relay step
- 測得 `Ku / Tu`
- 用 Ziegler-Nichols / Tyreus-Luyben 計算 PI
- 適合不同風扇或負載變化

## 方案 3：Feedforward + low-gain PI

- `target RPM -> reference ramp`
- `FF calibrated table + small PI correction`
- 低 duty 區 gain scheduling / Deadband / Anti-windup region-based tuning

## 方案 4：Integral Reset on Target Change

高價值、低成本改動：
- target changed → `s_integral = 0.0f`
- 通常可快速降低 overshoot

## 驗證 pipeline

1. Protocol: `A0`, manual P step, 3 repeats.
2. Run analysis script.
3. Run system ID.
4. Select 2-3 candidate PI only.
5. Re-run metrics.
6. Update `docs/TEST_RESULTS.md`.

## 已紀錄的 candidate (balanced)

- Estimated from manual P-steps:
  - median τ ≈ `0.43 s`
  - median θ ≈ `0.76 s`
  - Candidate `balanced`: KP ≈ `0.374`, KI ≈ `0.463`
  - Candidate `conservative`: KP ≈ `0.225`, KI ≈ `0.278`
- Current base: KP `0.20`, KI `0.70`
