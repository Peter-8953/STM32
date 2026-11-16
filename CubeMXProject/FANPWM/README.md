# FANPWM

STM32G4 風扇 PWM / RPM / 風速關係測試與分析專案。

## 目錄
- `Core/`, `Drivers/`, `EWARM/`：STM32 韌體與專案
- `scripts/`：分析/擷取 Python 腳本
- `data/`：量測資料與輸出（`data/output/`）
- `logs/`：串口擷取原始 log
- `docs/`：計畫、手冊與技術說明 (`docs/HANDBOOK.md`)
- `essay/`：參考文獻

## 快速開始
```powershell
python scripts/capture_mcu_csv.py COM4
python scripts/fan_wind_analysis.py
python scripts/fit_ff.py
```
