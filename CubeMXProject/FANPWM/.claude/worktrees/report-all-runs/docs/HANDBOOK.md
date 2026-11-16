# FANPWM 工作手冊（Persistent Handbook）

本手冊是本專案的 lived-in documentation，用來保存：
- 專案目標與已做過的事
- 韌體架構與檔案責任
- UART commands / 按鈕 / CSV 欄位
- 測試/量測/分析流程
- 控制工程建議路線
- 版控與 GitHub 約定

## 1. 專案目標
- 建立 STM32G4 風扇的 PWM / RPM / 風速關係。
- 在閉迴路 RPM 控制下，量化目標、實際、duty、風速。
- 以 version control 保存源碼、腳本與資料。

## 2. 已完成事項（chronology）
- 建立 Git repo 並 push 到 GitHub（origin/main）。
- PWM / RPM / 風速 relation CSV 產出。
- 閉迴路 RPM sweep 韌體實作與 IAR 專案修復。
- Python feedforward fit 與加密表。
- Root 整理：scripts/, data/, logs/, docs/, README。
- Step 1 baseline plan：停 sweep、清理按鈕、100ms CSV。
- Command reference 已建立。
- Add runtime toggle: `A0`, `A1`, `A` for automatic RPM sweep vs manual UART control.
- Auto/manual RPM test results recorded in `docs/TEST_RESULTS.md`.
- Analysis entry point: `scripts/analyze_rpm_test.py`.

## 3. 工作約束（user preference）
- **只在當前專案資料夾工作**；不跨出 `CubeMXProject/FANPWM`。
- 所有程式碼/腳本/分析結果都要 commit + push 到 GitHub。
- 先文件/計畫（handbook / plan）再實作。
- 重大改動前先做或更新計劃。

## 4. 韌體架構
- `Core/Inc/fan_control.h` / `Core/Src/fan_control.c`：PWM 與 tach 量測
- `Core/Inc/rpm_ctrl.h` / `Core/Src/rpm_ctrl.c`：閉迴路 RPM 控制
- `Core/Inc/rpm_sweep.h` / `Core/Src/rpm_sweep.c`：RPM 階梯 sweep
- `Core/Inc/fan_sweep.h` / `Core/Src/fan_sweep.c`：duty 階梯 sweep
- `Core/Inc/button_ui.h` / `Core/Src/button_ui.c`：按鈕操作
- `Core/Src/main.c`：初始化、主迴圈

## 5. UART Commands
- `R<rpm>`：閉迴路目標 RPM
- `P<pct>`：目標 = 滿轉速的 percent，不是 duty
- `D<duty>`：手動 duty（開迴路）
- `X`：目標 0
- `C`：重新校正
- `S`：狀態
- `T`：校正曲線
- `V`：切換 CSV logging
- `A0 / A1 / A`：關閉 / 啟用 / 切換 automatic RPM sweep

## 6. CSV Output
欄位：
`timestamp,target_rpm,actual_rpm,duty,ff,integral,ccr,per,rpm_min,rpm_max`

## 7. Measurement/Analysis Files
- Raw capture: `logs/COM4_*.csv/.txt`（可能含 serial 漏字/斷字）
- Cleaned rows: `logs/clean/COM4_*.csv`（由 `scripts/analyze_rpm_test.py` 生成）
- Sweep summaries: `data/output/COM4_*_sweep_detail.csv`, `..._sweep_summary.csv`
- Step metrics: `data/output/COM4_*_step_metrics.csv`
- PI candidates: `data/output/pi_sysid_candidates.csv`
- Wind data: `data/real12START_3CM.xls`
- Analysis outputs: `data/output/*.csv`

## 8. 常用測試/分析指令
手動執行步階：
```powershell
python scripts\send_step_protocol.py COM4 --hold 30 --repeats 3 --csv-on
python scripts\analyze_rpm_test.py logs\COM4_YYYYMMDD_HHMMSS.step.csv
```

固定測試協議：
1. `A0`
2. `P25` hold 30s
3. `P50` hold 30s
4. `P75` hold 30s
5. `P25` hold 30s
6. repeat 3 times

分析與整定：
```powershell
python scripts\analyze_rpm_test.py
python scripts\estimate_pi_from_steps.py logs/clean/COM4_*.csv
```

注意：
- COM port 不可與 Serial Monitor 同時开启
- 測試前應 build + flash Method B firmware
- V2 firmware parameters documented in `docs/TEST_RESULTS.md`

## 8. Control Method Summary
- 目前方法：校正 feedforward + PI，积分限幅、deadband、anti-windup、target ramp
- 優先升級方向：
  - 校正表加密（低 duty 區）
  - 降低 deadband / 增 I limit
  - step-response tuning（K/τ/θ）

## 9. Baseline Plan（Step 1）
- 暂停 sweep
- 清除舊按钮 callback
- CSV 100ms
- P25→P50→P75 步阶測試
- 產出 raw + analysis CSV

## 10. 備註
- GitHub: `https://github.com/Peter-8953/FANPWM`
- Current branch: `main`
- 本手冊每次有重要改變都要更新。
