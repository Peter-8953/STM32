# 圖表與原始資料對應表（Figure → Data Map）

| 圖檔 | 主要資料來源 | 產生脚本 |
|---|---|---|
| `data/output/pwm_rpm_wind_relation.png` | `data/output/pwm_rpm_wind_relation.csv` | `scripts/plot_pwm_rpm_wind.py` |
| `data/output/openloop_vs_closedloop_baseline.png` | `data/output/pwm_rpm_wind_relation.csv` + `logs/clean/COM4_2026_11_01.15.35.11.924.csv` | `scripts/plot_openloop_vs_closedloop.py` |
| `data/output/fig0_timeseries_check.png` | `data/real12START_3CM.xls`（風速計） | `scripts/12Start.py` |
| `data/output/fig1_duty_vs_windspeed.png` | duty sweep + 風速計 log | `scripts/12Start.py` |
| `data/output/fig2_linearity*.png` | duty / RPM / wind 穩定段 | `scripts/12Start.py` |
| `data/output/fig3_hysteresis.png` | up/down 風速迟滞 | `scripts/12Start.py` |
| `data/output/fig4_smoothness.png` | 風速時序 | `scripts/12Start.py` |
| `data/output/fig5_repeatability.png` | 重複 duty 階梯 | `scripts/12Start.py` |
| `data/output/fig6_pwm_velocity_flow.png` | duty / 風量 | `scripts/12Start.py` |
| `data/output/fig7_environment.png` | 溫溼度 / 風速 | `scripts/12Start.py` |
| `data/output/fig8_ramp_up_velocity_flow.png` | 上升 ramp 風速 / 風量 | `scripts/12Start.py` |
| `data/output/fig9_ramp_down_velocity_flow.png` | 下降 ramp 風速 / 風量 | `scripts/12Start.py` |
| `data/output/COM4_*.png` | 各次 step / sweep 測試 GUI 輸出 | IAR / 串口監看 / `analyze_rpm_test.py` |
| `data/output/*_step_metrics.csv` 對應 PNG | `logs/clean/COM4_*.csv` | `analyze_rpm_test.py` |
