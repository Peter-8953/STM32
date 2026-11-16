#ifndef RPM_CTRL_H
#define RPM_CTRL_H

#ifdef __cplusplus
extern "C" {
#endif

/* ======================= 自動校正 ========================================
 * 開機後自動把 duty 從 0% 掃到 100% (共 CAL_POINTS 點)，每一點等轉速穩定
 * 後記錄實測 RPM，得到「這顆風扇的 duty -> RPM 曲線」。
 * 最低轉速、最高轉速、前饋查表全部來自實測，程式裡沒有任何寫死的轉速上限。
 * 隨時可用 UART 指令 C 重新校正 (例如換風扇、改供電電壓之後)。
 *
 * 判穩方式：換 duty 後先等 CAL_SETTLE_MIN_MS (這段不採用)，之後每
 * CAL_WINDOW_MS 算一次視窗平均，連續 2 個視窗的平均值差在容許內才算穩定。
 * 每點最短約 4.9 秒 (SETTLE + 2 x WINDOW - 1 個控制週期)，整個校正約 55 秒。
 * 沒有 FG 訊號 (風扇沒在轉，或低於約 60 RPM) 的點記為 0 RPM，
 * 不會沿用被凍結的濾波值。每一點的結果會從 UART 印出，T 指令可再印整張表。 */
#define CAL_POINTS          11       /* 校正點數 (>=3)，duty 均分 0~100%       */
#define CAL_SETTLE_MIN_MS   3000U    /* 換 duty 後先等這麼久，這段轉速不採用   */
#define CAL_WINDOW_MS       1000U    /* 一個視窗的長度，取視窗內轉速平均       */
#define CAL_TOL_PCT         0.4f     /* 視窗平均值容許差：平均值的 0.4%        */
#define CAL_TOL_RPM         15.0f    /*   再加 15 RPM 的雜訊容許               */
#define CAL_TIMEOUT_MS      25000U   /* 每點最長等待，逾時取最後一個視窗平均   */
#define CAL_VALID_MIN_RPM   500.0f   /* 100% duty 仍低於此值 -> 校正失敗       */

/* ======================= 使用者滿轉 ======================================
 * P100 對應的 RPM。注意 P 是「轉速的百分比」，不是 duty 的百分比：
 * P20 = 20% x 使用者滿轉 (RPM)，再由校正表反查 duty。
 *   0    = 自動 (實測上限 x RPM_USER_HEADROOM)
 *   非 0 = 手動指定 (例如 16000.0f)，但不會超過實測上限                   */
#define RPM_FULL_USER_OVERRIDE  0.0f
#define RPM_USER_HEADROOM       0.97f   /* 留 3% 餘裕，高轉速時才有調節空間 */

/* ======================= 控制參數 ========================================
 * duty = 前饋 (由校正表反查) + KP x err + 積分。
 * err 以「整個轉速範圍 (max - min) 的百分比」表示，所以 KP 無單位、KI 單位 1/秒。
 * 迴路增益仍會隨該轉速區段的斜率 (RPM / 1% duty) 改變，斜率越陡增益越大；
 * 換風扇後若震盪或太慢再調 KP / KI (目前是編譯期常數，沒有 UART 指令)。   */
#define RPM_CTRL_PERIOD_MS  100U     /* 控制週期                              */
#define RPM_KP              0.18f    /* 2026-11-01 V2: 稍降 proportional，減少 overshoot */
#define RPM_KI              0.45f    /* 2026-11-01 V2: 降低 integral 防風大 overshoot */
#define RPM_I_LIMIT         6.0f     /* 2026-11-01 V2: windup upper limit */
#define RPM_FILTER_ALPHA    0.45f    /* 2026-11-01 V2: smoother tach measurement */
#define RPM_ERR_DEADBAND_PCT 0.5f    /* 積分死區 (% of RPM span)                  */
#define RPM_TARGET_RAMP_RPS  700.0f  /* V3: lower ramp for settle */

void  rpm_ctrl_init(void);              /* 啟動並開始自動校正                  */
void  rpm_ctrl_recalibrate(void);       /* 重新校正                            */

/* 設定目標。回傳 1 = 接受，0 = 校正中或校正失敗 (忽略)。
 * 超過實測上限的目標會被夾在上限。目標只變動 1 RPM 以內不會清積分。       */
int   rpm_ctrl_set_target(float rpm);
int   rpm_ctrl_set_percent(float pct);  /* 0~100% 的「使用者滿轉」             */

/* 手動 duty (開迴路)：直接指定實際輸出的 PWM duty，0.0 ~ 100.0 % (超出會夾住)。
 * 不經前饋與 PI，轉速仍會量測 (S 與 rpm_ctrl_get_rpm 看得到)。
 * 回傳 1 = 接受，0 = 校正中 (忽略)。
 * 之後呼叫 rpm_ctrl_set_target / set_percent (R / P / X 指令) 會回到閉迴路，
 * 重新校正 (C 指令) 也會結束手動模式。
 * 校正失敗 (ST_ERR) 時也能用：這時預設會全速 (保護)，手動 duty 會蓋過它；
 * 但 ST_ERR 下 R / P / X 不接受，只有 C 能離開手動模式。                    */
int   rpm_ctrl_set_duty(float duty_pct);
int   rpm_ctrl_is_manual(void);         /* 1 = 目前是手動 duty                 */
int   rpm_ctrl_is_calibrating(void);    /* 1 = 校正中                          */
int   rpm_ctrl_is_failed(void);         /* 1 = 校正失敗 (ST_ERR)               */
int   rpm_ctrl_is_csv_logging(void);  /* 1 = CSV logging mode                 */
void  rpm_ctrl_log(const char *s);      /* 從指令用的 UART 印一行文字 (blocking)，
                                           給 button_ui 這類模組回報動作用      */

float rpm_ctrl_get_target(void);
float rpm_ctrl_get_rpm(void);           /* 濾波後實際轉速，沒訊號回 0          */
float rpm_ctrl_get_duty(void);          /* 目前輸出 duty (%)                   */
float rpm_ctrl_get_min_rpm(void);       /* 實測：0% duty 的轉速                */
float rpm_ctrl_get_max_rpm(void);       /* 實測：100% duty 的轉速              */
float rpm_ctrl_get_full_user(void);     /* P100 對應的 RPM                     */
int   rpm_ctrl_is_ready(void);          /* 1 = 校正完成，可控制                */

void  rpm_ctrl_update(void);            /* 主迴圈呼叫，內部自己計時            */
void  rpm_ctrl_uart_poll(void);         /* 主迴圈呼叫，處理收到的整行指令      */
void  rpm_ctrl_print_status(void);      /* 可由主迴圈週期呼叫，自動印出 S 狀態 */

/* ======================= UART 指令 =======================================
 * 結尾換行，大小寫皆可：R<rpm> / P<pct> / D<duty> / S / X / C / T
 *   D<duty>  手動指定實際 PWM duty (0~100，可帶小數，例如 D17.31)。這個 duty 就是
 *            校正表橫軸的 duty (CCR = duty x (ARR+1) / 100)，開迴路，轉速只量測。
 *
 * S (RUN 狀態) 的輸出範例：
 *   OK target=1267 rpm=1268 duty=23.51% ff=22.97 i=0.55 ccr=1599/6800 range=0..4355 full=4225
 *   duty = ff + KP x err + i
 *   ff   = 由校正表反查的前饋 duty；i = 積分項 (穩態時就是校正表的殘差)
 *   ccr/週期 = 前風扇實際的 PWM 比例，應該跟 duty 一致 (不一致代表高解析度
 *              fan_set_duty_both_f() 沒生效)
 * S 在手動模式的輸出：
 *   MAN duty=17.31% rpm=848 ccr=1177/6800 range=0..4355 full=4225
 * 高解析度 duty 函式 fan_set_duty_both_f() 由 fan_control.c 提供。
 * 下指令後等 5~10 秒再送 S，才是穩態值。                                   */

#ifdef __cplusplus
}
#endif
#endif /* RPM_CTRL_H */
