# 資料收集 SOP

## 1. 擷取 MCU CSV

```powershell
python scripts\capture_mcu_csv.py COM4
```

## 2. 執行 step protocol

```powershell
python scripts\send_step_protocol.py COM4 --hold 30 --repeats 3 --csv-on
```

## 3. 清理 raw CSV

```powershell
python scripts\analyze_rpm_test.py logs\COM4_YYYYMMDD_HHMMSS.step.csv
```

## 4. 產生風速關係

```powershell
python scripts\fan_wind_analysis.py
```

## 5. 合併 / 聚合 RPM-PWM-wind

```powershell
python scripts\fan_rpm_pwm_wind.py
```

## 6. 產生圖表

```powershell
python scripts\plot_pwm_rpm_wind.py
python scripts\plot_openloop_vs_closedloop.py
```

主要输出在 `data/output/`；清理後的 raw logs 在 `logs/clean/`。