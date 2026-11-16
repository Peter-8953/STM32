#ifndef BUTTON_UI_H
#define BUTTON_UI_H

#ifdef __cplusplus
extern "C" {
#endif

/* ======================= 按鍵操作 =========================================
 * 用開發板的 USER 按鈕 (BUTTON_USER) 操作風扇，不用接 UART。
 *
 *   短按            閉迴路：P25 -> P50 -> P75 -> P100 -> 停 (目標 0) -> P25 ...
 *                   手動  ：D0 -> D10 -> D20 ... -> D100 -> D0 ...
 *                   階梯一律「找比目前實際值大的下一檔」，不另外存計數器，
 *                   所以和 UART 指令混用也不會錯位 (例如 R1267 後按一下 = P50)。
 *   長按 (>= 1 s)   放開時切換模式：
 *                     閉迴路 -> 手動：凍結目前輸出的 duty，風扇不會跳。
 *                     手動 -> 閉迴路：以目前實際轉速當目標，風扇不會跳。
 *   超長按 (>= 3 s) 按滿 3 秒就立刻重新校正 (等於 UART 的 C)，放開不再有動作。
 *
 *   校正中 (約 1 分鐘) 不接受任何按鍵；校正失敗時只接受超長按。
 *
 * LED (LED_GREEN)：
 *   手動模式恆亮、閉迴路熄滅；每接受一次按鍵反相閃一下；
 *   按住滿 1 秒也閃一下 (表示「現在放開就是長按」)；
 *   校正中快閃 (5 Hz)；校正失敗連閃 3 下、停一下、再重複。
 *
 * 用法：
 *   BSP_PB_Init / BSP_LED_Init 之後、rpm_ctrl_init() 之後呼叫 button_ui_init()；
 *   主迴圈每圈呼叫 button_ui_poll() (內部自己每 10 ms 取樣一次)。
 *   純輪詢，不需要 EXTI 中斷，也就不需要 BSP_PB_Callback。
 *   開機後 20 秒內是學習極性的時間 (見 BTN_PRESSED_LEVEL)，請讓按鈕保持放開。   */

#define BTN_POLL_MS         10U      /* 取樣週期                                  */
#define BTN_DEBOUNCE_MS     30U      /* 電位穩定這麼久才算按下 / 放開             */
#define BTN_LONG_MS         1000U    /* 長按門檻：放開時切換模式                  */
#define BTN_VERYLONG_MS     3000U    /* 超長按門檻：按滿就立刻重新校正            */
#define BTN_FLASH_MS        80U      /* 接受按鍵時 LED 反相閃一下的長度           */

/* 按下時的腳位電位：
 *   -1    = 自動學習極性：開機後 BTN_LEARN_MS 內持續取樣，多數時間的電位 = 放開電位。
 *           這段時間剛好是開機校正 (約 1 分鐘)，按鍵本來就鎖住；學完會從 UART 印
 *           一行 "BTN released level=..."，確認後可以把這裡固定成 0 / 1。
 *           只要開機後 10 秒內放開按鈕就不會判反。
 *   0 / 1 = 固定 (不學習，開機後立刻可用)。                                    */
#define BTN_PRESSED_LEVEL   (-1)
#define BTN_LEARN_MS        20000U

#define BTN_LOG             1        /* 1 = 每個動作用 UART 印一行 (BTN ...)      */

#define BTN_P_STEPS         25.0f, 50.0f, 75.0f, 100.0f   /* 閉迴路短按的階梯 (% 使用者滿轉) */
#define BTN_D_STEP          10.0f                         /* 手動模式短按的 duty 間隔 (%)    */

void button_ui_init(void);
void button_ui_poll(void);

#ifdef __cplusplus
}
#endif
#endif /* BUTTON_UI_H */
