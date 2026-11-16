# Feedforward / PI / Target Ramp 計算範例

本文件使用 `sub.csv` 中的一段資料，說明：

1. CSV 的 `target_rpm` 是命令目標，不是 controller 內部 `s_tgt_ramp`
2. Feedforward duty `ff` 是由 internal ramp target 查表得到
3. PI correction 使用 internal target，因此 duty / ff 可以 mismatch
4. raw data timeline 與 equation 的對照

---

## 1. CSV 的 `target_rpm` 是 setpoint，不是 `s_tgt_ramp`

在 `rpm_ctrl.c` 中有兩個不同 concept：

```text
s_target    : command setpoint，送 R2092 後立刻 = 2092.1
s_tgt_ramp  : controller 每 cycle 實際使用的 target，每 cycle 最多 +70 RPM
tgt         = s_tgt_ramp
```

看 raw row `1112915`：

```text
tick          = 1112915
target_rpm    = 2092.1   <- command setpoint
actual_rpm    = 1042.5
ff            = 20.70%
duty          = 21.14%
integral      = 0.09
```

Controller 實際使用的 `tgt` 不是 `2092.1`，而是 `s_tgt_ramp`。

若舊 target 大約是 `1046`，新命令 `2092`，第一個 cycle：

```text
s_tgt_ramp = 1046 + 70 = 1116
```

因此 feedforward duty 是：

```text
ff = ff_duty_from_rpm(1116) ≈ 20.70%
```

這就是 why `ff` 本例是 `20.70%`，而不是 lookup `2092.1` 得到的約 `36.93%`。

---

## 2. 因此 error 不能用 CSV `target_rpm` 來算

若用命令 target：

```text
err_dashboard = (2092.1 - 1042.5) × 100 / span
err_dashboard ≈ +24.3%
```

但这不是 controller 實際 error。控制器 actual 使用的是 `s_tgt_ramp ≈ 1116`：

```text
err ≈ (1116 - 1042.5) × 100 / 4314
err ≈ +1.7%
```

Then：

```text
duty ≈ ff + KP × err + integral
duty ≈ 20.70 + 0.18 × 1.70 + 0.09
duty ≈ 21.14%
```

與 raw data 的 `duty = 21.14%` 一致。

---

## 3. Control 順序解釋

```text
command R2092
  -> s_target = 2092.1          // command setpoint
  -> s_tgt_ramp from ≈ 1046 to ≈ 1116
  -> ff for 1116 ≈ 20.70%
  -> actual RPM ≈ 1042.5
  -> err ≈ +1.7%
  -> duty = ff + 0.18 × 1.7 + integral ≈ 21.14%
```

Mismatch 的原因是：

- CSV 的 `target_rpm` 是 setpoint
- controller 每 cycle 使用的 internal `s_tgt_ramp` 只是 slowly approaching target

---

## 4. Raw data timeline

| cycle | tick | CSV target | actual | duty | ff | integral |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 1112915 | 2092.1 | 1042.5 | 21.14 | 20.70 | 0.09 |
| 1 | 1113015 | 2092.1 | 1039.8 | 22.78 | 21.82 | 0.26 |
| 2 | 1113115 | 2092.1 | 1041.2 | 24.48 | 22.94 | 0.52 |
| 3 | 1113215 | 2092.1 | 1052.9 | 26.20 | 24.05 | 0.84 |
| 4 | 1113315 | 2092.1 | 1079.1 | 27.93 | 25.17 | 1.23 |
| 5 | 1113415 | 2092.1 | 1118.3 | 29.64 | 26.29 | 1.65 |
| 6 | 1113515 | 2092.1 | 1168.1 | 31.34 | 27.40 | 2.11 |
| 7 | 1113615 | 2092.1 | 1224.8 | 33.04 | 28.52 | 2.59 |
| 8 | 1113715 | 2092.1 | 1293.8 | 34.69 | 29.64 | 3.08 |
| 9 | 1113815 | 2092.1 | 1368.1 | 36.82 | 31.25 | 3.58 |
| 10 | 1113915 | 2092.1 | 1442.4 | 39.20 | 33.10 | 4.08 |
| 11 | 1114015 | 2092.1 | 1516.2 | 41.59 | 34.95 | 4.60 |
| 12 | 1114115 | 2092.1 | 1595.7 | 43.95 | 36.79 | 5.11 |
| 13 | 1114215 | 2092.1 | 1671.8 | 44.23 | 36.93 | 5.55 |
| 14 | 1114315 | 2092.1 | 1756.6 | 44.23 | 36.93 | 5.90 |

对应关系：

- `ff` 从 `20.70` 逐步升高到 `36.93`，说明 internal ramp 正在 toward `2092`
- `actual_rpm` 从 `1042.5` 快速 risen
- `integral` 從 `0.09` 快速 accumulation 正向，reach `5.90`
- 這段是 **acceleration assist** 阶段

---

## 5. duty 與 equation 的 approximate 对照

| cycle | s_tgt_ramp approx | ff | actual | err approx | KP*err approx | integral | duty approx |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0 | ~1116 | 20.70 | 1042.5 | +1.7% | +0.31 | 0.09 | 21.10 |
| 1 | ~1186 | 21.82 | 1039.8 | ~1.4% | +0.25 | 0.26 | 22.33 |
| 2 | ~1256 | 22.94 | 1041.2 | ~1.6% | +0.29 | 0.52 | 23.75 |
| ... | ... | ... | ... | ... | ... | ... | ... |

实际 raw 中的 `duty`（`21.14`、`22.78`、`24.48` ...）与估算可能略不同，主要 because：

1. `s_tgt_ramp` 不一定刚好是 `旧 target + 70n`
2. RPM filter
3. duty clamp / deadband
4. control cycle boundary 非整数

這不改变結論：**duty 使用 `s_tgt_ramp`，不是 CSV `target_rpm`。**

---

## 一句话总结

- `target_rpm` = command setpoint
- `s_tgt_ramp` = controller every cycle 的 controlled target
- `ff` = `ff_duty_from_rpm(s_tgt_ramp)`
- `duty` = `ff + KP × err + integral`
- 所以 mismatch duty ≈ `21.14`，是在 `s_tgt_ramp ≈ 1116` 的 basis 上计算，而不是 `2092.1`。