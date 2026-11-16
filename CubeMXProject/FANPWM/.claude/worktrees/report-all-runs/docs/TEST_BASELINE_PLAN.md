# 風扇控制基準線實驗計畫（Step 1）

本計畫目的：建立可重現的開迴路/閉迴路步階資料，作为 PID tuning 與規格驗收的依據。

## 目標
- 關閉自動 sweep，避免目標被覆寫。
- 移除舊按鈕 callback，避免兩套按鍵邏輯互相干擾。
- 將 CSV 取樣提升到至少 100–200 ms，能看見步階響應。
- 完成 P25→P50、P50→P75、P75→P25 步階測試，取得 K/τ/θ 估算與超調/ ổn態誤差。
- 產出可比較的 CSV 與圖表，並 commit 到 GitHub。

## 實驗流程

### 1. �韌體調整（只做必要、低風險修改）
- `main.c`：
  - 移除/停用 `BSP_PB_Callback`，改用 `button_ui_init()` / `button_ui_poll()`。
  - `BSP_PB_Init(COM? )` 改為 `BUTTON_MODE_GPIO`，避免 EXTI 中斷與 UI 競爭。
  - `rpm_ctrl_is_csv_logging()` 若不可用，直接在 main 狀態計時條件中用 100 ms 閾值。
- `main.c` 主迴圈：
  - 關閉 `rpm_sweep_update()` 呼叫（或註解）。
  - 開啟 `CSV logging ON` 時，每 100 ms 輸出一筆 CSV。
  - 保持 `rpm_ctrl_update()` 每 100 ms。

### 2. 測試條件
- 供電、風扇固定、環境溫度/風向固定。
- 每一個 step 至少 3 次重複，記錄：
  - open-loop step：固定 duty +5% 以上，每段 >= 10s
  - closed-loop step：目標 25→50→75→25，每段 >= 30s
- 每筆資料至少包含：`timestamp, target_rpm, actual_rpm, error, duty, ccr, per, rpm_min, rpm_max`

### 3. 資料分析
- 計算開迴路：K、τ、θ（一階 + 時延模型）。
- 計算閉迴路：rise time、settling time、overshoot、steady-state error、RPM ripple。
- 比較 up vs down step，觀察 hysteresis。

### 4. 驗收準則（spec）
- 10 Hz CSV 可重現步階。
- 目標 ±5% 以內 steady-state。
- Overshoot < 15%。
- Settling time < 2s（可調整）。
- 三次重複試驗的一致性（CV < 10%）。

## 交付物
- `fan_output/step_response_raw.csv`
- `fan_output/step_analysis.csv`
- `fan_output/openloop_fit.csv`
- Git commit + tag（例如 `step1-baseline`）

## 時程
- Day 0：韌體第 1 階段改動 + build
- Day 1：開迴路 step 資料收集
- Day 2：閉迴路 step 資料收集
- Day 3：分析 + 規格驗收 + commit

## 風險與注意
- 不要在 sweep 啟用時做 step 實驗。
- 按鈕 EXT 強制切到 GPIO polling，避免 event race。
- CSV 升高取樣率時，UART 傳輸量增加；堅持 115200 baud， 필요 시 log 使用 binary/off-line。
