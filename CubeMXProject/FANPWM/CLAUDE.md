# FANPWM 專案 AI 開發環境設定

本文件供 Claude Code 快速理解本專案背景、結構、command 與開發規則。

## 1. 專案概要

- MCU：STM32G4 (NUCLEO-G431RB 为主)
- 專案：FANPWM（PWM / RPM / 風速閉迴路控制）
- IDE / build：EWARM (IAR)
- 语言：C（FW）、Python（分析）
- 主要路徑：
  - `Core/`, `Drivers/`, `EWARM/`
  - `scripts/`
  - `data/`, `logs/`, `docs/`

## 2. 快速啟動

```powershell
python scripts\capture_mcu_csv.py COM4
python scripts\fan_wind_analysis.py
python scripts\plot_pwm_rpm_wind.py
```

## 3. 文件優先閱讀顺序

1. `docs/HANDBOOK.md`
2. `docs/DOCUMENTATION_INDEX.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DATA_COLLECTION_PROTOCOL.md`

如果 working on specific task:

- data analysis -> `docs/DATA_CATALOG.md`, `docs/FIGURE_DATA_MAP.md`
- control -> `docs/CLOSED_LOOP_CONTROL_METHOD.md`, `docs/CONTROL_CALCULATION_EXAMPLE.md`
- trouble -> `docs/TROUBLESHOOTING.md`

## 4. 編譯 / 韌體規則

- 勿把 duty 當作 target RPM；target 是 RPM，duty 是輸出
- 校正表 `cal_rpm[]` 是 volatile，開機重新校正
- 手動 duty (`D`) 为 open loop；送 `R`/`P`/`X` 可 resume closed loop
- 修改韌體後要 build、flash、追 log

## 5. 資料 / 分析規則

- `target_rpm` 是 setpoint，不是 internal ramp target
- raw logs 放 `logs/COM4_*.csv`
- cleaned logs 放 `logs/clean/`
- generated tables / plots 放 `data/output/`

## 6. 任務流程建議

1. Plan before edit（ especially firmware tuning）
2. 使用 small, isolated changes
3. commit + push only validated changes
4. update handbooks/docs after major changes

## 7. 文档 conventions

- docs md 一律使用繁體中文（Traditional Chinese）
- 引用 source files 使用 `path:line`
- cite raw data rows 时 give exact CSV rows
- newly added docs should be registered in `docs/DOCUMENTATION_INDEX.md`