# 文件索引

## 核心 handoff / handbook

- `HANDBOOK.md` — persistent handbook，包含 project goal、architecture、commands、baseline plan
- `ARCHITECTURE.md` — module / data flow / signal flow
- `USER_COMMANDS.md` — UART command set
- `GLOSSARY.md` — 常見術語

## 計劃 / 報告 / 結果

- `PROJECT_PLAN.md` — scope、milestones、backlog
- `PROJECT_SUMMARY.md` — concise summary
- `PROJECT_REPORT_WITH_EVIDENCE.md` — evidence report
- `TEST_BASELINE_PLAN.md` — test metrics 與 protocol
- `TEST_RESULTS.md` — actual measurement results
- `PI_TUNING_STRATEGY.md` — PI tuning findings
- `PWM_RPM_WIND_RELATIONSHIP.md` — duty/RPM/wind baseline

## 控制方法 / troubleshooting

- `CLOSED_LOOP_CONTROL_METHOD.md` — full control sequence
- `CONTROL_CALCULATION_EXAMPLE.md` — raw step calculation example
- `WHY_CLOSED_LOOP.md` — justification for closed loop
- `TROUBLESHOOTING.md` — common failure modes

## 資料 / data collection

- `DATA_CATALOG.md` — 所有 data files
- `FIGURE_DATA_MAP.md` — figure provenance
- `DATA_COLLECTION_PROTOCOL.md` — data collection SOP

## Data outputs

- `data/output/pwm_rpm_wind_relation.csv` — open-loop baseline
- `data/output/pwm_rpm_wind_model.csv` — calibrated model table
- `data/output/COM4_*` — raw step metrics / sweep tables

Overall rule:

- `HANDBOOK.md` for living pointer
- `DOCUMENTATION_INDEX.md` for navigation