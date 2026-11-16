# FANPWM 使用手冊（UART / 按鈕 / 資料栏位）

## UART 指令
- `R<rpm>`：設定目標 RPM（閉迴路）。例如 `R2000`
- `P<pct>`：設定目標 = 滿轉速的 percent（`P` 不是 PWM duty）。例如 `P30` = 30% 滿轉（≈ 1250–1260 RPM）
- `D<duty>`：手動 duty（開迴路），`D17.5` = duty 17.5%
- `X`：目標 0（風扇跑到最低轉速）
- `C`：重新校正
- `S`：印出狀態
- `T`：印出校正曲線表（duty→RPM）
- `V`：切換 CSV logging（ON/OFF）
- `A0` / `A1` / `A`：關閉 / 啟用 / 切換 automatic RPM sweep

## 按鈕
- 短按：閉迴路 `P25 → P50 → P75 → P100 → 停`；手動模式 duty +10%
- 長按：切換閉迴路 ↔ 手動模式
- 超長按：重新校正

## CSV 輸出（當 `V` ON）
`timestamp,target_rpm,actual_rpm,duty,ff,integral,ccr,per,rpm_min,rpm_max`
- `target_rpm`：目標轉速
- `actual_rpm`：濾波後實際轉速
- `duty`：輸出 PWM %
- `ff`：feedforward duty %
- `integral`：積分項
- `ccr/per`：PWM 計數/週期
- `rpm_min/rpm_max`：校正範圍

## 重要觀念
- `P20` / `P30` 是目標 RPM percent，不是 PWM duty。
- `D20` 是 PWM duty 20%（開迴路）。
- GPIO/EXTI 事件可能造成目標被外部 callback 改掉；目前 Step 1 已停用舊 callback，避免 race。
- `A0` 停用 automatic sweep 後，R/P/D/X 才可穩定手動控制；否則 automatic sweep 會每 30 s 覆寫目標。
