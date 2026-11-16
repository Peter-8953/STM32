# 故障排除指南

## 没有 RPM 訊號 / 校正失败

- 檢查 FG pull-up 到 3.3 V
- 檢查 PA0 / PA1 配線
- 檢查 `TACH_TIMER_CLOCK_HZ` 是否為 170000000
- 風扇低于约 120 RPM 可能 timeout

## PWM duty 没變化

- 檢查 TIM ARR / CCR 輸出
- 檢查 `fan_set_duty_both_f()` 的 CCR 更新是否生效
- 檢查是否处于 manual mode（`D<duty>` 会啟用；送 `R` / `P` / `X` 可退出）

## 閉迴路 overshoot / hunting

- 提高 `RPM_FILTER_ALPHA`
- 降低 `RPM_KI`
- 提高 `RPM_ERR_DEADBAND_PCT`
- 降低 `RPM_TARGET_RAMP_RPS`

## 高 duty 供電下 sag warning

- 校正步驟中若 RPM 隨 duty 提高反而掉落，韧體會 warning
- 可能是高 duty 下風扇供電不足
- 檢查供電電流能力

## Raw data 清理

- 使用 `analyze_rpm_test.py` 清理 `logs/COM4_*.csv`
- 檢查 serial 漏字、斷字、 malformed rows