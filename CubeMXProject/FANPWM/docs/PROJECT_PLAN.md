# FANPWM 專案計畫（PWM / RPM / 風速關係分析）

## 1. 專案目標
- 建立 STM32G4 風扇系統的測試、分析與版控流程。
- 量化以下關係：
  - PWM duty (%) ↔ RPM
  - 目標 RPM ↔ 實際 RPM
  - RPM / duty ↔ 風速 (m/s)
- 以 version control 保存韌體、腳本與量測資料，便於回溯與重現。

## 2. 專案目錄與主要檔案

### 韌體（`Core/` + `Drivers/`）
- `Core/Inc/fan_control.h` / `Core/Src/fan_control.c`：PWM 與 tach 驅動，duty 0–100%，RPM 量測。
- `Core/Inc/rpm_ctrl.h` / `Core/Src/rpm_ctrl.c`：閉迴路 RPM 控制器（校正 + feedforward + PI）。
- `Core/Inc/rpm_sweep.h` / `Core/Src/rpm_sweep.c`：RPM 階梯 sweep（0→100%→10%，每階 60 s，100% 120 s）。
- `Core/Inc/fan_sweep.h` / `Core/Src/fan_sweep.c`：開迴路 duty 階梯 sweep（0→100%→12%）。
- `Core/Inc/button_ui.h` / `Core/Src/button_ui.c`：USER 按鈕操作與模式切換。
- `Core/Src/main.c`：系統初始化、主迴圈（呼叫 `rpm_ctrl_update`、`rpm_sweep_update`、按鈕輪詢、狀態列印）。
- `Drivers/`：STM32G4xx HAL、BSP、CMSIS。

### 分析腳本
- `capture_mcu_csv.py`：串口擷取 MCU CSV，加上 PC 時間戳。
- `fan_rpm_pwm_wind.py`：MCU CSV 與風速計 log 合併、依 duty 聚合。
- `fan_wind_analysis.py`：依 sweep dwell 分段計算每階風速，輸出 relation CSV。
- `fit_ff.py`：擬合 duty→RPM，產生加密 FF 表。

### 資料與輸出
- `mcu_clean.csv`、`COM4_*.csv`：MCU/串口擷取資料。
- `real12START_3CM.xls`：風速計 log。
- `fan_output/*.csv`、`*.png`：分析結果與圖表。
- `essay/`：參考文獻與 txt。

### 版控 / 建置
- `.gitignore`：忽略 EWARM 建置產物、Python cache 等。
- `EWARM/FANPWM.ewp`：IAR 專案檔。
- `PROJECT_PLAN.md`：本計畫。

## 3. 控制與量測方法
- **任務 A：低轉速啟動校正**
  - Probe 1→20% duty，直到 RPM > 50，記錄最小起動 duty/RPM。
- **任務 B：duty-RPM 校正**
  - duty 0–100%，每點穩定後取視窗平均。
  - 單調化，記錄 `cal_rpm[]`。
- **/tasks C：閉迴路 RPM 控制**
  - feedforward（表格插值）+ PI。
  - 目標斜坡、積分限幅、死區、anti-windup。
- **任務 D：steady-state characterization**
  - RPM sweep 0→100%→10%，每階 60 s；100% 120 s。
  - 擷取 `(tick, target_rpm, rpm, duty, ccr, per)`。

## 4. 資料分析流程
1. 擷取 MCU CSV（含 `pc_time` 或 raw 10 欄）。
2. 擷取風速計 Excel（Date/Time/Value）。
3. 用 `fan_rpm_pwm_wind.py` 或 `fan_wind_analysis.py` 合併並按 duty/RPM 聚合。
4. 輸出：
   - `fan_output/fan_test_steps.csv`
   - `fan_output/pwm_rpm_wind_relation.csv`
   - `fan_output/ff_duty_to_rpm_dense.csv`
   - `fan_output/ff_rpm_to_duty.csv`

## 5. 時程 / 已完成項目
- Day 0：建立 Git repo、baseline commit、push GitHub。
- Day 1：PWM duty sweep 分析、風速資料整理。
- Day 2：閉迴路 RPM sweep 實作、IAR 專案更新、build 修正。
- Day 3：RPM sweep 量測與 CSV 分析。
- Day 4：feedforward Python fit、加密表與 PID 參數建議。
- Day 5：計畫文件化、版控同步。

## 6. 改進方向（Backlog）
- 密化 `CAL_POINTS` / 低 duty 網格。
- 調整 `RPM_ERR_DEADBAND_PCT`、`RPM_I_LIMIT`、`RPM_KI`。
- Gain scheduling / adaptive tuning。
- 高解析 tach 或更長 averaging window。
- 在 device 端使用更平滑的 FF interpolation（PCHIP/ monotonic）。

## 7. 版本控制政策
- 所有代碼/腳本/分析結果在測試前後提交 Git。
- 韌體變更必須附 build 結果與 commit message。
- 大版本使用 tag（如 `v0.1-rpm-sweep`）。
