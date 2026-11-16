# 說明 / Glossary（中文版）

| 名詞 | 說明 |
|---|---|
| `s_target` | 命令目標 RPM |
| `s_tgt_ramp` | 經過斜坡/ramp 後的控制目標 RPM |
| `cal_rpm[]` | 每一點 duty 的量測稳態 RPM |
| `ff` | 由 `cal_rpm` 反查的 feedforward duty |
| `integral` | PI 的積分項，單位 `% duty` |
| `span` | `rpm_max - rpm_min` |
| `deadband` | 很小的誤差範圍內，integral 不更新或衰減 |
| manual duty | 開迴路模式，由 `D<duty>` 直接設定 duty |
| resume closed loop | 送 `R` / `P` / `X`，返回闭迴路 |