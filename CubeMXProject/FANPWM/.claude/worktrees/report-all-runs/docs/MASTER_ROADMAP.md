# FANPWM 文件總整與執行順序（Master Roadmap）

## 一、讀檔順序
1. HANDBOOK.md — 操作指令（UART/按鈕/CSV欄位）
2. USER_COMMANDS.md — 命令與校正/模式
3. PROJECT_SUMMARY.md — 專案全貌
4. TEST_BASELINE_PLAN.md — baseline 條件
5. TEST_RESULTS.md — 目前測試結果
6. PI_TUNING_STRATEGY.md — 調參策略/安全護欄
7. ALL_RUNS_SUMMARY_REPORT.md — 所有 run 摘要
8. IMPROVEMENT_PLAN.md — 接下來 phased improvement
9. MASTER_ROADMAP.md — 本總索引

---

## 二、階段狀態

### Phase 0 — 基礎（DONE）
- 韌體 scaffold（main/rpm_ctrl/rpm_sweep/button_ui）
- PWM/RPM 量測
- PI baseline（KP .18 / KI .45 / I 6 / alpha .45 / ramp 800）
- sweep 30s + runtime A toggle
- clean pipeline + protocol 工具

### Phase 1 — steady tracking（PARTIAL）
- 中/高 RPM（1040–4173）steady PASS
- **FAIL**：417 RPM（+7.9% err，ripple 53）
- 低轉速 FF / tach 量測需修

### Phase 2 — step dynamics（FAIL gate）
- overshoot 10–30%
- settle 3–8s（spec <2s）
- 下階步 worse（7–8s + 大下衝）
- 0→417 嚴重（overshoot 65–72%，settle 29.8s）

### Phase 3 — improvements（PENDING）
- instrumentation（PI 事件 log）
- 低轉速 FF table
- integral/deadband/anti-windup
- PI candidates（balanced/conservative）
- ramp/transition shaping
- standardized 3-repeat acceptance

---

## 三、已完成 vs 待執行

### 已完成
- 韌體 scaffold + models
- steady-state tracking (mid/high)
- data pipeline (raw/clean/summary/step)
- baseline report + all-runs report
- improvement plan doc

### 待執行（按優先序）
1. Phase 0 baseline freeze + clean run archive
2. Phase 1 instrumentation patch (no control change)
3. Phase 2 low-RPM FF targeted test + table
4. Phase 3 integral conditioning (one change at a time)
5. Phase 4 PI candidate experiments (3-repeat)
6. Phase 5 ramp/transition shaping
7. Phase 6 acceptance gates + manifest

---

## 四、關鍵數字（快速參考）

| 指標 | 目前 |
|---|---|
| 417 RPM steady | FAIL (+7.9%, ripple 53) |
| 中/高 RPM steady | PASS (<±1%) |
| Upward settle | 3–6s（spec <2s） |
| Downward settle | 7–8s |
| Overshoot | 10–30%（spec <15%） |
| 0→417 | 29.8s settle |

---

## 五、關鍵檔案
- `docs/HANDBOOK.md`
- `docs/USER_COMMANDS.md`
- `docs/PROJECT_SUMMARY.md`
- `docs/TEST_BASELINE_PLAN.md`
- `docs/TEST_RESULTS.md`
- `docs/PI_TUNING_STRATEGY.md`
- `docs/ALL_RUNS_SUMMARY_REPORT.md`
- `docs/IMPROVEMENT_PLAN.md`
- `scripts/send_step_protocol.py`
- `scripts/analyze_rpm_test.py`
- `scripts/analyze_speed_log.py`

---

## 六、下一步（單一行動）
先做 **Phase 1 instrumentation**，再跑一次 **3-repeat baseline**，把 PI 事件 log 補齊，之後所有 tuning 才有診斷依據。