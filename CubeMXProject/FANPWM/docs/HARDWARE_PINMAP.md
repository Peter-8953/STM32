# 硬體接腳與設定（`fan_control.h`）

| 訊號 | STM32 接腳 / Timer | 功能 |
|---|---|---|
| 前風扇 PWM | PC0 / TIM1_CH1 | PWM 輸出 |
| 後風扇 PWM | PC6 / TIM8_CH1 | PWM 輸出 |
| 前風扇 tach FG | PA0 / TIM2_CH1 | RPM 輸入捕获 |
| 後風扇 tach FG | PA1 / TIM2_CH2 | RPM 輸入捕获 |

## 設定

- PWM：25 kHz、edge-aligned
- Tach timer clock：170 MHz
- 每轉脈衝：2
- Tach timeout：250 ms（约 120 RPM 以下可能 reported 0）

每個 FG open-collector 線都需要独立接 3.3 V pull-up。