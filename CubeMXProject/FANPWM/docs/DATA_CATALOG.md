# 資料與圖表分類目錄（Data Catalog）

本目錄用來釐清 `data/`、`logs/`、`data/output/` 內各檔案的意義、來源與收集方式。
若要重新產生某類資料，請對照「產生/收集方式」欄位。

## 0. 資料來源總覽

| 來源 | 路徑 | 收集方式 |
|---|---|---|
| MCU / 韌體 UART CSV | `logs/COM4_*.csv`, `logs/COM4_*.txt` | STM32 串口輸出，`scripts/capture_mcu_csv.py` 擷取並加上 PC 時間戳 |
| 清洗後 MCU CSV | `logs/clean/COM4_*.csv` | `scripts/analyze_rpm_test.py` 清除漏字 / 斷字 / 異常列 |
| 風速計 log | `data/real12START_3CM.xls` | 風速計匯出 Excel（Function = VEL） |
| Open-loop duty sweep 量測 | `fan_sweep.c` / `fan_wind_analysis.py` 輸出 | duty 階梯 0→100→12%，每階穩定段取風速 |
| Closed-loop RPM step 測試 | `send_step_protocol.py` + MCU CSV | P25→P50→P75 等目標 RPM 階梯 |
| 校正 / Feedforward | `fit_ff.py` | 從 MCU CAL log 提取 duty→RPM 並 PCHIP 擬合 |
| PI tuning | `estimate_pi_from_steps.py` | 從 cleaned step CSV 估 Kp/Ki |

## 1. 原始資料（Raw Acquisition）

| 檔案 | 意義 | 收集/產生方式 |
|---|---|---|
| `logs/COM4_YYYYMMDD_HHMMSS.csv` / `.txt` | 串口原始擷取，可能含缺字 | `capture_mcu_csv.py COM4` |
| `logs/clean/COM4_*.csv` | 清洗後的 100 ms CSV | `analyze_rpm_test.py` |
| `data/mcu_clean.csv` | 小型 MCU CSV 樣本 | 手動整理 / 測試用 |
| `data/real12START_3CM.xls` | 風速計原始 Excel log | 風速計匯出，Function=VEL |
| `data/output/sub.csv`, `sub.png`, `sub.txt`, `wlog.txt` | 臨時 / exploratory 輸出 | 個別分析腳本產生，未正式納入 pipeline |

## 2. 開迴路基準資料（Open-loop Baseline）

| 檔案 | 意義 | 產生方式 |
|---|---|---|
| `data/output/pwm_rpm_wind_relation.csv` | duty / RPM / up/down wind 的主對照表 | `scripts/fan_wind_analysis.py` |
| `data/output/rpm_pwm_wind.csv` | RPM / duty / wind 上下平均 aggregating 版本 | `scripts/fan_rpm_pwm_wind.py` |
| `data/output/step_table.csv` | 每個 duty 階梯的穩定段風速 | `fan_wind_analysis.py` |
| `data/output/environment_by_duty.csv` | 溫溼度 / 風速迟滞環境記錄 | `fan_wind_analysis.py` / 12Start 風格分析 |
| `data/output/hysteresis.csv` | 迟滞統計 | `fan_wind_analysis.py` |
| `data/output/linearity_summary.csv` | 線性度統計 | `fan_wind_analysis.py` / 12Start |
| `data/output/pwm_airflow_table.csv` | duty→風速/風量換算表（含 mph/km/h/CMM/CFM/CMS） | `fan_wind_analysis.py` / 12Start |
| `data/output/pwm_airflow_table_up.csv` / `_down.csv` | 上升 / 下降方向風量表 | `fan_wind_analysis.py` / 12Start |
| `data/output/pwm_airflow_table.xlsx` | Excel 版風量表 | 匯出 |

## 3. 閉迴路 / Step 測試結果

|---|---|---|
| `data/output/COM4_*_step_metrics.csv` | 每個 step 的追蹤 metrics | `analyze_rpm_test.py` |
| `data/output/COM4_*_sweep_detail.csv` | RPM sweep 每階段 detail | sweep log analysis |
| `data/output/COM4_*_sweep_summary.csv` | sweep 摘要 | sweep log analysis |
| `data/output/fan_test_steps.csv` | fan 流程逐步結果 | `fan_wind_analysis.py` |
| `data/output/summary_per_step.csv` | 每 step 摘要 | step analysis |
| `data/output/step_change_comparison.csv` | step 變化比較 | step analysis |
| `data/output/pi_sysid_candidates.csv` | PI 參數候選 | `estimate_pi_from_steps.py` |

## 4. 衍生模型與擬合

| 檔案 | 意義 | 產生方式 |
|---|---|---|
| `data/output/ff_duty_to_rpm_dense.csv` | duty→RPM 密化 feedforward 表 | `scripts/fit_ff.py` |
| `data/output/ff_rpm_to_duty.csv` | 目標 RPM→feedforward duty 表 | `scripts/fit_ff.py` |
| `data/output/pwm_rpm_wind_model.csv` | 量測值 + poly3/PCHIP/best linear 模型 + 殘差 | `scripts/fit_pwm_rpm_wind.py` |
| `data/output/pwm_rpm_wind_fit_summary.csv` | 擬合公式係數與 R² | `scripts/fit_pwm_rpm_wind.py` |

## 5. 圖表（Figures）

| 檔案 | 意義 | 產生方式 |
|---|---|---|
| `data/output/fig0_timeseries_check.png` | 時序 sanity check | 12Start 風格分析 |
| `data/output/fig1_duty_vs_windspeed.png` | duty vs 風速 | 12Start 風格分析 |
| `data/output/fig2_linearity.png` 系列 | 線性度總圖與局部圖 | 12Start 風格分析 |
| `data/output/fig3_hysteresis.png` | 上升 / 下降迟滞 | 12Start 風格分析 |
| `data/output/fig4_smoothness.png` | 平滑度 | 12Start 風格分析 |
| `data/output/fig5_repeatability.png` | 重複性 | 12Start 風格分析 |
| `data/output/fig6_pwm_velocity_flow.png` | PWM / 風量關係 | 12Start 風格分析 |
| `data/output/fig7_environment.png` | 環境記錄 | 12Start 風格分析 |
| `data/output/fig8_ramp_up_velocity_flow.png` | 上升 ramp 風速 / 風量 | 12Start 風格分析 |
| `data/output/fig9_ramp_down_velocity_flow.png` | 下降 ramp 風速 / 風量 | 12Start 風格分析 |
| `data/output/COM4_*.png` | 各次測試 GUI / plot 輸出 | 測試流程 / 串口監看 |
| `data/output/pwm_rpm_wind_relation.png` | duty/RPM/wind 關係圖 | `scripts/plot_pwm_rpm_wind.py` |
| `data/output/openloop_vs_closedloop_baseline.png` | 開迴路 baseline vs 閉迴路追蹤 | `scripts/plot_openloop_vs_closedloop.py` |

## 6. 建議閱讀順序

1. 先看 `data/output/pwm_rpm_wind_relation.csv`：了解 duty / RPM / wind 的開迴路基準。
2. 再看 `data/output/pwm_rpm_wind_model.csv` / `fit_summary.csv`：取得擬合公式。
3. 若要解释閉迴路，看 `docs/WHY_CLOSED_LOOP.md` 與 `openloop_vs_closedloop_baseline.png`。
4. 調整 PI 時，先看 `logs/clean/` 與 `pi_sysid_candidates.csv`。
