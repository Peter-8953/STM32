# FANPWM 軟體結構 / 資料流總覽

## 1. 主要模組

| 模組 | 責任 |
|---|---|
| `fan_control.c` | PWM 輸出、tach RPM 量測、callback |
| `rpm_ctrl.c` | 閉迴路控制、校正、feedforward、PI、ramp |
| `rpm_sweep.c` | 自動 RPM step sweep / mode toggle |
| `fan_sweep.c` | 開迴路 duty step sweep |
| `button_ui.c` | USER 按鈕 action / status |
| `main.c` | init、main loop、呼叫 `rpm_ctrl_update()`、poll UART / buttons |

## 2. 控制資料流

```text
target command
  -> s_target
  -> s_tgt_ramp
  -> ff_duty_from_rpm()
  -> PI
  -> duty clamp
  -> fan_set_duty_both_f()
  -> TIM1 / TIM8 PWM
  -> fan FG tach
  -> measure_rpm()
  -> rpm filter
  -> err calculation
  -> integral update
```

## 3. 校正資料流

```text
cal_start()
  -> cal_duty[] = 0, 10, ..., 100%
  -> every duty point measures steady RPM
  -> cal_rpm[] filled, then monotonic in cal_finish()
  -> s_rpm_min / s_rpm_max selected
  -> feedforward table ready
```

## 4. 測試資料流

```text
MCU CSV output
  -> capture_mcu_csv.py -> logs/COM4_*.csv
  -> analyze_rpm_test.py -> logs/clean/*.csv
  -> scripts/*.py aggregate / fit
  -> data/output/*.csv/*.png
  -> docs/*.md report
```