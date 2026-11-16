#include "button_ui.h"
#include "main.h"                 /* BSP_PB_GetState / BSP_LED_*、HAL_GetTick */
#include "rpm_ctrl.h"
#include <math.h>                 /* floorf */
#include <stdio.h>

#define BTN_DEBOUNCE_TICKS  ((BTN_DEBOUNCE_MS + BTN_POLL_MS - 1U) / BTN_POLL_MS)

static const float k_p_steps[] = { BTN_P_STEPS };
#define K_P_STEPS_N  (sizeof k_p_steps / sizeof k_p_steps[0])

#if (BTN_PRESSED_LEVEL < 0)
static uint8_t  s_released_level = 0U;   /* 放開時的腳位電位 (開機後學到的)   */
static uint32_t s_n_level[2];            /* 學習期間，各電位的取樣次數        */
static uint32_t s_t_init    = 0U;
static uint8_t  s_learned   = 0U;
#endif
static uint8_t  s_stable    = 0U;        /* 去彈跳後的狀態，1 = 按下          */
static uint8_t  s_cnt       = 0U;        /* 去彈跳計數                        */
static uint32_t s_t_press   = 0U;        /* 這次按下的時間                    */
static uint8_t  s_mark_long = 0U;        /* 已經按滿 BTN_LONG_MS (閃過一次了) */
static uint8_t  s_consumed  = 0U;        /* 這次按壓已處理 / 被鎖住，放開不再動作 */
static uint32_t s_last_poll = 0U;
static uint32_t s_flash_end = 0U;
static uint8_t  s_led       = 0xFFU;     /* 0xFF = 尚未輸出過，第一次一定會更新 */

/* ---- 回報 ---------------------------------------------------------------- */
static void say(const char *s)
{
#if BTN_LOG
  rpm_ctrl_log(s);
#else
  (void)s;
#endif
}

/* ---- 讀按鈕 -------------------------------------------------------------- */
static uint8_t level_now(void)
{
  return (BSP_PB_GetState(BUTTON_USER) != 0) ? 1U : 0U;
}

static uint8_t pressed_raw(void)
{
#if (BTN_PRESSED_LEVEL >= 0)
  return (level_now() == (uint8_t)BTN_PRESSED_LEVEL) ? 1U : 0U;
#else
  return (level_now() != s_released_level) ? 1U : 0U;
#endif
}

/* ---- LED ----------------------------------------------------------------- */
static void flash(uint32_t now) { s_flash_end = now + BTN_FLASH_MS; }

static void led_update(uint32_t now)
{
  uint8_t on;

  if (rpm_ctrl_is_calibrating())
  {
    on = (uint8_t)((((now / 100U) & 1U) == 0U) ? 1U : 0U);        /* 5 Hz 快閃 */
  }
  else if (rpm_ctrl_is_failed())
  {
    uint32_t ph = now % 2000U;                                    /* 連閃 3 下，停到 2 秒 */
    on = (uint8_t)(((ph < 900U) && ((ph % 300U) < 150U)) ? 1U : 0U);
  }
  else
  {
    on = rpm_ctrl_is_manual() ? 1U : 0U;                          /* 手動恆亮，閉迴路熄滅 */
    if ((int32_t)(s_flash_end - now) > 0) on = (uint8_t)(on ? 0U : 1U);   /* 反相閃一下 */
  }

  if (on != s_led)
  {
    s_led = on;
    if (on) { BSP_LED_On(LED_GREEN); }
    else    { BSP_LED_Off(LED_GREEN); }
  }
}

/* ---- 動作 ---------------------------------------------------------------- */
/* 目前目標佔「使用者滿轉」的百分比 */
static float target_percent(void)
{
  float full = rpm_ctrl_get_full_user();
  return (full > 1.0f) ? (100.0f * rpm_ctrl_get_target() / full) : 0.0f;
}

/* 閉迴路短按：找比目前大的下一檔 P；已在最高一檔就停 (目標 0)；停著就從最低一檔開始 */
static void step_closed(uint32_t now)
{
  char  msg[64];
  float cur  = target_percent();
  float next = -1.0f;

  for (unsigned i = 0U; i < K_P_STEPS_N; i++)
  {
    if (k_p_steps[i] > cur + 0.5f) { next = k_p_steps[i]; break; }
  }

  if (next < 0.0f)
  {
    if (!rpm_ctrl_set_target(0.0f)) return;
    snprintf(msg, sizeof msg, "BTN short: stop (target=0)\r\n");
  }
  else
  {
    if (!rpm_ctrl_set_percent(next)) return;
    snprintf(msg, sizeof msg, "BTN short: P%.0f -> target=%.0f RPM\r\n",
             (double)next, (double)rpm_ctrl_get_target());
  }
  say(msg);
  flash(now);
}

/* 手動短按：duty 加一格 (BTN_D_STEP)，超過 100% 回到 0% */
static void step_manual(uint32_t now)
{
  char  msg[64];
  float cur  = rpm_ctrl_get_duty();
  float next = (floorf((cur + 0.5f) / BTN_D_STEP) + 1.0f) * BTN_D_STEP;
  if (next > 100.01f) next = 0.0f;

  if (!rpm_ctrl_set_duty(next)) return;
  snprintf(msg, sizeof msg, "BTN short: D%.0f -> duty=%.2f%%\r\n",
           (double)next, (double)rpm_ctrl_get_duty());
  say(msg);
  flash(now);
}

/* 長按：閉迴路 <-> 手動。兩個方向都不讓風扇跳一下 */
static void toggle_mode(uint32_t now)
{
  char msg[64];

  if (!rpm_ctrl_is_manual())
  {
    float d = rpm_ctrl_get_duty();                       /* 凍結目前輸出的 duty */
    if (!rpm_ctrl_set_duty(d)) return;
    snprintf(msg, sizeof msg, "BTN long: manual, duty=%.2f%% (frozen)\r\n", (double)d);
  }
  else
  {
    if (!rpm_ctrl_set_target(rpm_ctrl_get_rpm())) return;  /* 以目前實際轉速當目標 */
    snprintf(msg, sizeof msg, "BTN long: closed loop, target=%.0f RPM\r\n",
             (double)rpm_ctrl_get_target());
  }
  say(msg);
  flash(now);
}

static void do_recalibrate(void)
{
  if (rpm_ctrl_is_calibrating()) return;
  rpm_ctrl_recalibrate();
  say("BTN very long: recalibrating (about 1 min)\r\n");
}

/* ---- 事件 ---------------------------------------------------------------- */
static void on_press(uint32_t now)
{
  s_t_press   = now;
  s_mark_long = 0U;
  s_consumed  = 0U;

  if (rpm_ctrl_is_calibrating())                  /* 校正中：整次按壓都不理 */
  {
    s_consumed = 1U;
    say("BTN ignored: calibrating\r\n");
  }
}

static void on_hold(uint32_t now)
{
  if (s_consumed) return;

  uint32_t held = now - s_t_press;

  if (!s_mark_long && held >= BTN_LONG_MS)        /* 提示：現在放開 = 長按 */
  {
    s_mark_long = 1U;
    flash(now);
  }
  if (held >= BTN_VERYLONG_MS)                    /* 超長按：按滿就動作，放開不再處理 */
  {
    s_consumed = 1U;
    do_recalibrate();
  }
}

static void on_release(uint32_t now)
{
  if (s_consumed) return;

  if (rpm_ctrl_is_failed())                       /* 校正失敗：短按 / 長按都不接受 */
  {
    say("BTN ignored: calibration failed, hold 3 s to recalibrate\r\n");
    return;
  }

  if ((now - s_t_press) >= BTN_LONG_MS)      toggle_mode(now);
  else if (rpm_ctrl_is_manual())             step_manual(now);
  else                                       step_closed(now);
}

/* ---- 對外 ---------------------------------------------------------------- */
void button_ui_init(void)
{
#if (BTN_PRESSED_LEVEL < 0)
  s_n_level[0] = 0U;
  s_n_level[1] = 0U;
  s_t_init     = HAL_GetTick();
  s_learned    = 0U;
#endif
  s_stable    = 0U;
  s_cnt       = 0U;
  s_consumed  = 1U;
  s_last_poll = HAL_GetTick();
  s_led       = 0xFFU;
}

void button_ui_poll(void)
{
  uint32_t now = HAL_GetTick();
  if ((now - s_last_poll) < BTN_POLL_MS) return;
  s_last_poll = now;

#if (BTN_PRESSED_LEVEL < 0)
  if (!s_learned)                      /* 開機後先學習極性，這段時間不處理按鍵 */
  {
    s_n_level[level_now()]++;
    if ((now - s_t_init) >= BTN_LEARN_MS)
    {
      char msg[48];
      s_released_level = (s_n_level[1] > s_n_level[0]) ? 1U : 0U;   /* 多數時間的電位 = 放開 */
      s_learned = 1U;
      s_stable  = 0U;
      s_cnt     = 0U;
      snprintf(msg, sizeof msg, "BTN released level=%u\r\n", (unsigned)s_released_level);
      say(msg);
    }
    led_update(now);
    return;
  }
#endif

  uint8_t raw = pressed_raw();
  if (raw == s_stable)
  {
    s_cnt = 0U;
  }
  else if (++s_cnt >= BTN_DEBOUNCE_TICKS)         /* 連續幾次取樣都不同才算變化 */
  {
    s_cnt    = 0U;
    s_stable = raw;
    if (raw) on_press(now);
    else     on_release(now);
  }

  if (s_stable) on_hold(now);
  led_update(now);
}
