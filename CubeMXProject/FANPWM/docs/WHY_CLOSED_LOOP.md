# 為什麼需要閉迴路 RPM 控制（以 raw data 為 baseline）

## 1. 開迴路 baseline：PWM duty 只能“大致”對應風速 / RPM

由 `pwm_rpm_wind_relation.csv` 的量測可看到：

- duty 0→100% 時，RPM 從 0 升到 4309，呈現非線性且前段斜率大、後段斜率小；
- 相同 duty 下，上升 / 下降遲滞最大可達 0.1875 m/s；
- duty / RPM / 風速之間沒有單一固定比例，低 duty 區（12–30%）最容易產生 RPM 漂移。

換句話說，**把 duty 固定在某一值，並不等於把系統鎖在某一 RPM 或風速**。供電變化、溫度變化、軸承摩擦、不同個體風扇都會讓同一 duty 對應的 RPM 改變。

## 2. 閉迴路如何用 raw data 證明有效

閉迴路測試（例如 `logs/clean/COM4_2026_11_01.15.35.11.924.csv`）中，控制器把 duty 當成被控輸出，實際 RPM 作為回授，目標 RPM 作為命令。

從 raw run 可觀察到：

- 目標 RPM 從 0 逐步升到 4173，actual RPM 緊跟目標；
- settled 區段 MAE 約 17.9 RPM；
- duty 不是固定值，而是隨著目標與實際 RPM 差異自動調整（例如 target ≈ 1046 時 duty 約 19.7%，target ≈ 3149 時 duty 約 64.5%）；
- feedforward 先給近似 duty，PI / 積分項補償残差，steady-state duty 與 target 對應的 calibration point 接近。

## 3. 一句話結論

開迴路 baseline 證明 **PWM duty 與 RPM / 風速只是經驗校正曲線**；閉迴路控制把 duty 轉成被控量，直接以 **目標 RPM** 為命令，吸收電壓、個體差、遲滞與外部擾動，因此更適合需要穩定風量 / 風速的應用。

## 4. 圖表

`data/output/openloop_vs_closedloop_baseline.png`：包含開迴路 duty sweep、閉迴路追蹤、duty 自動調整、以及各 target 的 steady-state error。
