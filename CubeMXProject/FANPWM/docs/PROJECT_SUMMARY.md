# FANPWM 風扇閉迴路控制專案總整理（標题與子標题）

## 1. 專案目標
### 1.1 主目標
- 建立 STM32G4 風扇的 PWM / RPM / 風速關係。
- 完成閉迴路 RPM 控制驗證。
- 量化 target、actual、duty、ff、integral、ripple。

### 1.2 副目標
- 建立可重現測試流程。
- 將韌體、資料、腳本與報告版控。
- 建立 auto/manual 切換與可追蹤分析 pipeline。

## 2. 專案範圍
### 2.1 韌體
- `Core/Inc` / `Core/Src`
- `main.c` / `rpm_ctrl.c` / `rpm_sweep.c`
- `button_ui.c`
- `fan_control.c`

### 2.2 分析與資料
- MCU CSV capture
- 風速計 Excel
- `scripts/analyze_rpm_test.py`
- clean data / summary / step metrics

### 2.3 文檔
- `PROJECT_PLAN.md`
- `TEST_BASELINE_PLAN.md`
- `USER_COMMANDS.md`
- `HANDBOOK.md`
- `TEST_RESULTS.md`
- `PI_TUNING_STRATEGY.md`

## 3. 系統流程
### 3.1 初始化
- HAL_Init / SystemClock / peripherals
- TIM1 / TIM8 / TIM2 / GPIO
- `fan_control_init()`
- `rpm_ctrl_init()`
- `rpm_sweep_init()`
- `button_ui_init()`

### 3.2 主迴圈
- `rpm_ctrl_update()`
- `rpm_sweep_update()`
- `rpm_ctrl_uart_poll()`
- `button_ui_poll()`
- CSV/status periodic logging

### 3.3 模式切換
- auto sweep mode
- manual UART mode（`A0`）
- return auto sweep（`A1`）

## 4. 控制方法
### 4.1 閉迴路控制
- target: `R<rpm>` / `P<pct>`
- actual: tach RPM
- feedforward + PI
- PWM output

### 4.2 目前參數（V2 基準）
- `RPM_KP = 0.18f`
- `RPM_KI = 0.45f`
- `RPM_I_LIMIT = 6.0f`
- `RPM_FILTER_ALPHA = 0.45f`
- `RPM_TARGET_RAMP_RPS = 800.0f`
- `RPM_ERR_DEADBAND_PCT = 0.5f`

### 4.3 Scaffold / Configuration
- integral reset on target change
- anti-windup
- feedforward interpolation
- target ramp

### 4.4 Sweep Characterization
- `0 → 10 → … → 100 → … → 10`
- 基本 dwell 30s
- 100% dwell 60s
- runtime A toggle on / off

## 5. 量測與分析流程
### 5.1 Raw Capture
- serial port
- MCU CSV rows
- raw log archive

### 5.2 Clean / Validate
- filter malformed numeric lines
- remove range-invalid rows
- normalize 10 columns
- chronological order

### 5.3 Derived Outputs
- sweep steady-state summaries
- step response metrics
- PI candidate sysID
- generated analysis CSV files

### 5.4 Scripts
- `send_step_protocol.py`: auto P25/P50/P75 sequence
- `analyze_rpm_test.py`: clean + sweep + step
- `estimate_pi_from_steps.py`: FOPTD + PI candidate generation

## 6. 測試協議
### 6.1 步驟
1. `A0`
2. `P25` hold 30s
3. `P50` hold 30s
4. `P75` hold 30s
5. `P25` hold 30s
6. repeat 3 times

### 6.2 評估指標
- Steady-state error：±5%
- Overshoot：`< 15%`
- Settling time：`< 2s`
- RPM ripple
- 3-repeat CV：`< 10%`

## 7. 已完成項目
### 7.1 韌體 / Git
- Git repo + GitHub `main`
- PWM / RPM default config
- Closed-loop PI tuning
- Sweep 30s re-enabled（目前 V2 基準）
- Method B runtime toggle
- PI V2 灌入 constants
- SysID candidate script
- auto protocol tooling

### 7.2 分析與報告
- Clean CSV pipeline
- Sweep summary CSV
- Step metrics CSV
- `TEST_RESULTS.md`
- `PI_TUNING_STRATEGY.md`
- `HANDBOOK.md`
- `USER_COMMANDS.md`

### 7.3 韌體修改 tracked
- `Core/Inc/rpm_ctrl.h`
- `Core/Inc/rpm_sweep.h`
- `Core/Src/rpm_ctrl.c`
- `Core/Src/rpm_sweep.c`
- `Core/Src/main.c`

## 8. 測試結果（概要）
### 8.1 Auto Sweep 穩態
- 0 RPM：PASS
- 417 RPM：FAIL（`+7.86%`，ripple 53）
- 834 RPM：PASS（`+2.22%`）
- 1251+ RPM：基本 PASS（±1%）

### 8.2 Manual Step Baseline
- steady-state error：mostly pass
- overshoot：10-27%
- settle：3-7s
- ripple 通常 <10 RPM

### 8.3 V2 Run
- overshoot：12-15%
- settle：1.8-4.8s
- steady-state：PASS
- improvement vs baseline：overshoot 全面 downshift

### 8.4 V3 Run
- ramp lowering attempted
- settle 无改善
- overshoot slightly worse on P50→P75
- conclusion：revert to V2 ramp 800 作为 baseline

## 9. 目前identified问题
### 9.1 Overshoot
- P50→P75 ~14.9-15.4%
- P25→P50 ~12.6%
- still near 15% boundary

### 9.2 Settling Time
- P25→P50 ~4.4-4.8s
- P50→P75 ~1.8-3.4s
- spec <2s 未完全 meet

### 9.3 Low RPM
- 417 RPM fail
- low duty FF insufficient
- tach ripple influence still

### 9.4 Workflow / consistency
- Repeat evidence needed
- Avoid brute-force tuning
- baseline must stable first

## 10. 下一步建議
### 10.1 立即 action
- 使用 clean 3-repeat protocol
- Keep V2 as baseline（KP 0.18, KI 0.45, I 6, ALPHA 0.45, RAMP 800）
- Ramp candidate for micro adjustment: ramp 800→700
- Evaluate Ki 0.45→0.40 only if necessary

### 10.2 System Identification
- FOPTD median tau ≈ 0.43s
- theta ≈ 0.76s
- balanced candidate：KP≈0.374, KI≈0.463
- conservative candidate：KP≈0.225, KI≈0.278

### 10.3 Low RPM / Feedforward
- P10/P15/P20 step test
- low-duty FF table calibration
- region-specific gain/deadb Depression
- high ripple investigation

### 10.4 Reporting
- append protocol run to `TEST_RESULTS.md`
- maintain script-generated analysis outputs
- commit validated firmware and report only
EOF