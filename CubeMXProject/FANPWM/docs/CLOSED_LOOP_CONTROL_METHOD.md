# FANPWM 閉迴路 RPM 控制方法報告

本報告說明 `rpm_ctrl.c` 的閉迴路控制架構、自動校正流程、控制方程式，以及量測資料如何被使用。

---

## 1. 控制目標

本系統使用 NUCLEO-G431RB 控制風扇，量測方式為 tachometer FG 信號轉換成 RPM。

控制目標不是直接指定 PWM duty，而是指定 **目標 RPM**。MCU 會自動调整 PWM duty，使實際 RPM 追上目標。

這可避免：

- 固定 duty 對應 RPM 的非線性與漂移
- 供電变化造成轉速变化
- 温度、個體差造成同一 duty 有不同 RPM
- 高 / 低 duty 斜率差异導致控制難度不同

---

## 2. 系統架構

```text
Target RPM
   |
   v
RPM ramp (700 RPM/s)
   |
   v
Feedforward duty (from calibration table)
   |
   v
PI correction (KP * error + integral)
   |
   v
Duty clamp (0..100%)
   |
   v
PWM output (TIM1 / TIM8)
   |
   v
Fan speed
   |
   v
Tach FG -> RPM measurement
   |
   +----> low-pass filter -> error calculation
```

---

## 3. 開機自動校正：建立 duty -> RPM 曲線

### 3.1 校正點數

使用：

```c
#define CAL_POINTS 11
```

校正點：

```text
0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100%
```

### 3.2 校正流程

每個 duty 點的流程：

1. 輸出指定 duty
2. 等待 `CAL_SETTLE_MIN_MS = 3000 ms`
3. 每 `CAL_WINDOW_MS = 1000 ms` 取一次視窗平均
4. 連續兩個視窗平均值差在容許範圍內，判定穩定
5. 單點逾時 `CAL_TIMEOUT_MS = 25000 ms` 則取最後視窗平均
6. 記錄 `cal_rpm[point]`

最低有效 RPM：

```c
#define CAL_VALID_MIN_RPM 500.0f
```

100% duty 若仍低於這個值，校正失敗。

### 3.3 單調處理

校正完成後強制曲線單調不減：

```c
for (i = 1; i < CAL_POINTS; i++)
{
    if (cal_rpm[i] < cal_rpm[i-1]) cal_rpm[i] = cal_rpm[i-1];
}
```

然後設定：

```c
s_rpm_min = cal_rpm[0];
s_rpm_max = cal_rpm[CAL_POINTS - 1];
```

---

## 4. 量測得到的校正曲線

| PWM duty | RPM | wind up (m/s) | wind down (m/s) |
|---:|---:|---:|---:|
| 0% | 0 | 0.000 | — |
| 12% | 509 | 1.187 | 1.223 |
| 20% | 1042 | 2.269 | 2.306 |
| 30% | 1795 | 3.564 | 3.573 |
| 40% | 2221 | 4.362 | 4.324 |
| 50% | 2629 | 5.186 | 5.142 |
| 60% | 3007 | 5.762 | 5.814 |
| 70% | 3378 | 6.431 | 6.386 |
| 80% | 3763 | 7.235 | 7.047 |
| 90% | 4038 | 7.695 | 7.646 |
| 100% | 4309 | 8.162 | — |

來源檔案：

- `data/output/pwm_rpm_wind_relation.csv`
- 韌體 runtime：`s_rpm_min`, `s_rpm_max`, `cal_duty[]`, `cal_rpm[]`

---

## 5. Feedforward：由目標 RPM 反查 duty

校正表是：

```text
duty 0%  -> 0 RPM
duty 10% -> 509 RPM
...
duty 100% -> 4309 RPM
```

控制時需要反過來：目標 RPM -> duty。

MCU 使用 `ff_duty_from_rpm()` 做線性内插：

```c
static float ff_duty_from_rpm(float rpm)
{
    if (rpm <= cal_rpm[0]) return 0.0f;
    if (rpm >= cal_rpm[CAL_POINTS - 1]) return 100.0f;

    for (i = 0; i < CAL_POINTS - 1; i++)
    {
        lo = cal_rpm[i];
        hi = cal_rpm[i + 1];
        if (rpm <= hi)
        {
            return cal_duty[i] +
                   (rpm - lo) / (hi - lo) *
                   (cal_duty[i + 1] - cal_duty[i]);
        }
    }
    return 100.0f;
}
```

因此：

```text
target RPM -> feedforward duty
```

---

## 6. 控制方程式

控制週期：

```c
#define RPM_CTRL_PERIOD_MS 100U
```

每 100 ms 執行一次。

### 6.1 RPM 濾波

```c
meas = average RPM from front/rear tach
s_fg_ok = (meas >= 1.0) ? 1 : 0

if (s_fg_ok)
    s_rpm_f = s_rpm_f + ALPHA * (meas - s_rpm_f)
```

參數：

```c
RPM_FILTER_ALPHA = 0.45
```

### 6.2 目標斜坡

```c
step = RPM_TARGET_RAMP_RPS * dt

if (s_tgt_ramp < s_target)
    s_tgt_ramp = min(s_tgt_ramp + step, s_target)
else if (s_tgt_ramp > s_target)
    s_tgt_ramp = max(s_tgt_ramp - step, s_target)
```

參數：

```c
RPM_TARGET_RAMP_RPS = 700.0
```

### 6.3 誤差

```text
err = (target - measured_rpm) * 100 / (rpm_max - rpm_min)
```

### 6.4 PI 控制

```c
if (fabs(err) < RPM_ERR_DEADBAND_PCT)
    s_integral *= 0.90

i_new = clamp(
    s_integral + KI * err * dt,
    -RPM_I_LIMIT,
    +RPM_I_LIMIT
)

duty = ff + KP * err + i_new
```

參數：

```text
KP = 0.18
KI = 0.45
RPM_I_LIMIT = 6.0
RPM_ERR_DEADBAND_PCT = 0.5
```

### 6.5 Anti-windup

```c
if (duty >= 100.0)
{
    duty = 100.0;
    if (err > 1.0) s_flag = FL_HIGH;
    s_integral *= 0.85;
}
else if (duty < 0.0)
{
    duty = 0.0;
}
else
{
    s_integral = i_new;
}
```

避免 output 飽和時 integral 無限累積。

---

## 7. 主要控制流程

```text
rpm_ctrl_update() runs every 100 ms
1. measure RPM
2. low-pass filter RPM
3. if calibration: run calibration step
4. if manual: output manual duty directly
5. if calibration failed: output 100%
6. ramp target RPM
7. ff = ff_duty_from_rpm(target)
8. if no FG signal: output ff + integral only
9. calculate err = (target - rpm) * 100 / span
10. apply deadband, PI, anti-windup
11. clamp duty 0..100
12. fan_set_duty_both_f(duty)
```

---

## 8. UART 指令

| 指令 | 功能 |
|---|---|
| `R<rpm>` | 設定目標 RPM |
| `P<pct>` | 設定目標為滿轉速百分比 |
| `D<duty>` | 手動 duty，開迴路 |
| `X` | 目標 0 |
| `C` | 重新校正 |
| `S` | 顯示狀態 |
| `T` | 印出校正曲線 |
| `V` | CSV logging on/off |
| `A0 / A1 / A` | auto sweep off / on / toggle |

查看校正曲線：

```text
T
```

會輸出：

```text
T0 duty=0.0% rpm=0
T1 duty=10.0% rpm=...
...
```

---

## 9. 為何需要閉迴路

grade open-loop baseline：

- duty 0% -> 0 RPM
- duty 12% -> 509 RPM
- duty 100% -> 4309 RPM

但固定 duty 不保證固定 RPM，因為：

```text
供電变化
個體風扇差异
溫度
軸承摩擦
遲滯
```

閉迴路控制直接以目標 RPM 為命令，MCU 根據實測 RPM 調整 duty，因此更稳定。

---

## 10. 測試結果摘要

使用一組 closed-loop run，settled 區段誤差約：

| Target RPM | Actual RPM | Duty | RPM std |
|---:|---:|---:|---:|
| 417 | 441 | 11.02 | 46.35 |
| 835 | 842 | 17.35 | 15.30 |
| 1252 | 1249 | 22.59 | 4.05 |
| 1669 | 1653 | 28.71 | 20.08 |
| 2086 | 2089 | 36.76 | 6.32 |
| 2504 | 2494 | 47.11 | 6.42 |
| 2921 | 2916 | 57.70 | 1.57 |
| 3338 | 3348 | 68.90 | 2.07 |
| 3755 | 3739 | 80.14 | 4.56 |
| 4173 | 4152 | 96.19 | 5.22 |

---

## 11. 相關檔案

| 檔案 | 說明 |
|---|---|
| `Core/Src/rpm_ctrl.c` | 閉迴路控制實作 |
| `Core/Inc/rpm_ctrl.h` | 參數與 API |
| `Core/Src/fan_control.c` | PWM / tach 量測 |
| `Core/Src/main.c` | 主迴圈呼叫 `rpm_ctrl_update()` |
| `data/output/pwm_rpm_wind_relation.csv` | 開迴路 baseline 量測 |
| `data/output/pwm_rpm_wind_relation.png` | 關係圖 |
| `docs/WHY_CLOSED_LOOP.md` | 為何需要閉迴路控制 |
| `docs/DATA_CATALOG.md` | 資料檔案分類 |

---

## 12. 結論

本系統使用：

```text
on-device calibration
+ feedforward from cal_rpm[]
+ PI correction
+ RPM ramp
+ deadband
+ integral windup protection
```

因此可以由目標 RPM 穩定控制風扇轉速，而不是直接依賴固定 PWM duty。
MD
echo done
