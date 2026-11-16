#include "rpm_ctrl.h"
#include "main.h"
#include "rpm_sweep.h"
#include "fan_control.h"
#include "tim.h"                  /* htim1：S 指令讀實際的 CCR / ARR */
#include <math.h>                 /* fabsf */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* COM1 的 UART handle 由 BSP 提供 (stm32g4xx_nucleo.h 內 extern) */
#define CMD_UART       (&hcom_uart[COM1])
/* NUCLEO-G431RB / G474RE 的 COM1 都是 LPUART1；若你的板子不同請改這裡 */
#define CMD_UART_IRQn  LPUART1_IRQn

typedef enum { ST_CAL = 0, ST_RUN, ST_ERR } state_t;
typedef enum { FL_OK = 0, FL_LOW, FL_HIGH, FL_NOFG } flag_t;

static void print_status(void);
static state_t  s_state    = ST_CAL;
static flag_t   s_flag     = FL_OK;

static float    s_target   = 0.0f;   /* 目標 RPM                                    */
static float    s_tgt_ramp = 0.0f;   /* 斜坡後目標 RPM (用於控制)                     */
static float    s_rpm_f    = 0.0f;   /* 濾波後 RPM (沒訊號時凍結，要搭配 s_fg_ok 看) */
static float    s_ff       = 0.0f;   /* 前饋 duty (%)，由校正表反查；S 指令顯示用    */
static float    s_integral = 0.0f;   /* 積分項 (% duty)                             */
static float    s_duty     = 0.0f;   /* 輸出 duty (%) = ff + KP*err + 積分           */
static uint32_t s_last_ms  = 0;
static uint8_t  s_fg_ok    = 0;      /* 1 = 這個週期有量到轉速 (FG 有訊號)           */
static uint8_t  s_manual      = 0;      /* 1 = 手動 duty (開迴路)：不跑前饋 / PI          */
static uint8_t  s_log_csv     = 0;      /* 1 = CSV logging 模式                           */
static float    s_manual_duty = 0.0f;   /* 手動指定的實際 PWM duty (%)                    */

/* ---- 校正結果 (全部來自實測) ------------------------------------------ */
static float    s_rpm_min  = 0.0f;   /* 0%   duty 的轉速  */
static float    s_rpm_max  = 0.0f;   /* 100% duty 的轉速  */
static float    cal_duty[CAL_POINTS];
static float    cal_rpm [CAL_POINTS];
static uint8_t  s_cal_idx  = 0;
static uint8_t  s_probe_duty = 0U;
static uint8_t  s_probe_found = 0U;
static uint32_t s_probe_t0 = 0U;
static float    s_probe_rpm = 0.0f;
static uint32_t s_cal_t0   = 0;      /* 這一點開始的時間        */
static uint32_t s_cal_win  = 0;      /* 目前視窗的起點          */
static float    s_cal_sum  = 0.0f;   /* 目前視窗內轉速的累加    */
static uint16_t s_cal_n    = 0;      /* 目前視窗內的取樣數      */
static float    s_cal_prev = -1.0f;  /* 上一個視窗的平均 (<0 = 還沒有) */

/* ---- UART 接收 (中斷逐 byte，行結尾 \n 或 \r) -------------------------- */
static uint8_t           s_rx_byte;
static char              s_line[24];
static volatile uint8_t  s_line_len = 0;
static char              s_cmd[24];
static volatile uint8_t  s_cmd_ready = 0;

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart != CMD_UART) return;

  char c = (char)s_rx_byte;
  if (c == '\n' || c == '\r')
  {
    if (s_line_len > 0 && !s_cmd_ready)
    {
      s_line[s_line_len] = '\0';
      memcpy(s_cmd, s_line, (size_t)s_line_len + 1U);
      s_cmd_ready = 1;
    }
    s_line_len = 0;
  }
  else if (s_line_len < sizeof(s_line) - 1U)
  {
    s_line[s_line_len++] = c;
  }
  HAL_UART_Receive_IT(CMD_UART, &s_rx_byte, 1);
}

static void uart_print(const char *s)
{
  HAL_UART_Transmit(CMD_UART, (uint8_t *)s, (uint16_t)strlen(s), 50);
}

/* ---- 小工具 ------------------------------------------------------------ */
static float clampf(float v, float lo, float hi)
{
  return (v < lo) ? lo : ((v > hi) ? hi : v);
}

/* 前後風扇都有訊號取平均，只有一顆有訊號就用那一顆，都沒有回 0 */
static float measure_rpm(void)
{
  float f = fan_get_front_rpm();
  float r = fan_get_rear_rpm();
  if (f > 1.0f && r > 1.0f) return 0.5f * (f + r);
  if (f > 1.0f) return f;
  if (r > 1.0f) return r;
  return 0.0f;
}

/* ---- 自動校正 ---------------------------------------------------------- */
static void cal_point_begin(uint32_t now)
{
  s_cal_t0   = now;
  s_cal_win  = now;
  s_cal_sum  = 0.0f;
  s_cal_n    = 0;
  s_cal_prev = -1.0f;
}

static void cal_start(void)
{
  for (uint8_t i = 0; i < CAL_POINTS; i++)
  {
    cal_duty[i] = 100.0f * (float)i / (float)(CAL_POINTS - 1);
    cal_rpm[i]  = 0.0f;
  }
  s_state    = ST_CAL;
  s_flag     = FL_OK;
  s_cal_idx  = 0;
  s_integral = 0.0f;
  s_ff       = 0.0f;
  s_manual   = 0U;                       /* 重新校正會結束手動模式 */
  s_tgt_ramp = 0.0f;
  s_probe_duty  = 0U;
  s_probe_found = 0U;
  s_probe_t0    = HAL_GetTick();
  s_probe_rpm   = 0.0f;
  cal_point_begin(HAL_GetTick());
}

static void cal_log_point(uint8_t idx, float rpm, uint32_t since_ms, uint8_t timed_out)
{
  char out[100];
  snprintf(out, sizeof out,
           "CAL %u/%u duty=%.1f%% rpm=%.0f (f=%.0f r=%.0f) t=%.1fs%s\r\n",
           (unsigned)(idx + 1U), (unsigned)CAL_POINTS, (double)cal_duty[idx],
           (double)rpm, (double)fan_get_front_rpm(), (double)fan_get_rear_rpm(),
           (double)since_ms / 1000.0, timed_out ? " TIMEOUT" : "");
  uart_print(out);
}

static void cal_finish(void)
{
  char out[112];

  /* duty 增加轉速卻掉下來 -> 通常是風扇電源在高 duty 時撐不住 */
  for (uint8_t i = 1; i < CAL_POINTS; i++)
  {
    if (cal_rpm[i] < 0.95f * cal_rpm[i - 1U])
    {
      snprintf(out, sizeof out,
               "WARN rpm drops at %.0f%% duty (%.0f -> %.0f): fan supply sagging?\r\n",
               (double)cal_duty[i], (double)cal_rpm[i - 1U], (double)cal_rpm[i]);
      uart_print(out);
    }
  }

  /* 曲線強制單調不減 (去掉量測雜訊造成的小反轉) */
  for (uint8_t i = 1; i < CAL_POINTS; i++)
  {
    if (cal_rpm[i] < cal_rpm[i - 1U]) cal_rpm[i] = cal_rpm[i - 1U];
  }
  s_rpm_min = cal_rpm[0];
  s_rpm_max = cal_rpm[CAL_POINTS - 1U];

  if (s_rpm_max < CAL_VALID_MIN_RPM || s_rpm_max < 1.2f * s_rpm_min)
  {
    snprintf(out, sizeof out,
             "CAL FAILED: max rpm=%.0f, no FG signal or fan not powered? send C to retry\r\n",
             (double)s_rpm_max);
    uart_print(out);
    s_state = ST_ERR;
    return;
  }

  if (s_target > s_rpm_max) s_target = s_rpm_max;
  s_integral = 0.0f;
  s_flag     = FL_OK;
  s_state    = ST_RUN;

  snprintf(out, sizeof out, "CAL done: min=%.0f max=%.0f full(P100)=%.0f\r\n",
           (double)s_rpm_min, (double)s_rpm_max, (double)rpm_ctrl_get_full_user());
  uart_print(out);
}

/* 每個控制週期呼叫一次：輸出目前這一點的 duty。
 * 換 duty 後先等 CAL_SETTLE_MIN_MS，之後每 CAL_WINDOW_MS 取一次視窗平均，
 * 連續兩個視窗的平均值差在容許內才算穩定，記錄後換下一點。               */
static void cal_step(uint32_t now)
{
  /* startup probe: 1% steps until RPM > 50, then log minimum start duty/RPM */
  if (!s_probe_found)
  {
    if (s_probe_duty == 0U)
    {
      s_probe_duty = 1U;
      s_probe_t0 = now;
      fan_set_duty_both_f(0.0f);
      s_duty = 0.0f;
      return;
    }
    fan_set_duty_both_f((float)s_probe_duty);
    s_duty = (float)s_probe_duty;
    if ((now - s_probe_t0) < 1500U)
    {
      return;
    }
    float meas = measure_rpm();
    if (meas > 50.0f)
    {
      s_probe_rpm = meas;
      s_probe_found = 1U;
      char out[80];
      snprintf(out, sizeof out, "START duty=%u%% rpm=%.0f (f=%.0f r=%.0f)\r\n",
               (unsigned)s_probe_duty, (double)meas, (double)fan_get_front_rpm(), (double)fan_get_rear_rpm());
      uart_print(out);
      return;
    }
    if ((now - s_probe_t0) >= 2000U)
    {
      if (s_probe_duty >= 20U)
      {
        s_probe_found = 1U;
        s_probe_rpm = 0.0f;
        uart_print("START not found below 20%, fallback to normal calibration\n");
        return;
      }
      s_probe_duty++;
      s_probe_t0 = now;
    }
    return;
  }
  float duty = cal_duty[s_cal_idx];
  s_duty = duty;
  fan_set_duty_both_f(duty);

  /* 沒有 FG 訊號 = 風扇沒在轉 (或低於約 60 RPM)。這時 s_rpm_f 是被凍結的舊值，
   * 不能當量測值，否則 0% / 10% 會記到一個假的轉速。                         */
  float cur = s_fg_ok ? s_rpm_f : 0.0f;

  uint32_t since     = now - s_cal_t0;
  float    value     = cur;
  uint8_t  accept    = 0;
  uint8_t  timed_out = 0;

  if (since < CAL_SETTLE_MIN_MS)
  {
    s_cal_win = now;                       /* 剛換 duty，這段不採用 */
  }
  else
  {
    s_cal_sum += cur;
    s_cal_n++;

    if ((now - s_cal_win) >= CAL_WINDOW_MS)
    {
      float mean = s_cal_sum / (float)s_cal_n;
      float tol  = CAL_TOL_PCT * 0.01f * mean + CAL_TOL_RPM;
      float d    = mean - s_cal_prev;
      if (d < 0.0f) d = -d;

      value = mean;
      if (s_cal_prev >= 0.0f && d <= tol) accept = 1;

      s_cal_prev = mean;                   /* 開下一個視窗 */
      s_cal_sum  = 0.0f;
      s_cal_n    = 0;
      s_cal_win  = now;
    }
  }

  if (!accept && since >= CAL_TIMEOUT_MS)
  {
    accept    = 1;                         /* 逾時：取最後一個視窗平均 */
    timed_out = 1;
    if (s_cal_prev >= 0.0f) value = s_cal_prev;
  }
  if (!accept) return;

  /* 低於啟動 duty 的點應視為 0 RPM，避免減速殘值汙染校正表 */
  if ((float)s_probe_duty > 0.0f && cal_duty[s_cal_idx] < (float)s_probe_duty)
  {
    value = 0.0f;
  }

  cal_rpm[s_cal_idx] = value;
  cal_log_point(s_cal_idx, value, since, timed_out);

  s_cal_idx++;
  if (s_cal_idx >= CAL_POINTS)
  {
    cal_finish();
    return;
  }
  cal_point_begin(now);
}

/* 由目標 RPM 反查 duty：在實測曲線上線性內插 */
static float ff_duty_from_rpm(float rpm)
{
  if (rpm <= cal_rpm[0])                 return 0.0f;
  if (rpm >= cal_rpm[CAL_POINTS - 1U])   return 100.0f;

  for (uint8_t i = 0; i < CAL_POINTS - 1U; i++)
  {
    float lo = cal_rpm[i];
    float hi = cal_rpm[i + 1U];
    if (rpm <= hi)
    {
      if ((hi - lo) < 1.0f) return cal_duty[i + 1U];
      return cal_duty[i] + (rpm - lo) / (hi - lo) * (cal_duty[i + 1U] - cal_duty[i]);
    }
  }
  return 100.0f;
}

/* ---- 對外介面 ---------------------------------------------------------- */
void rpm_ctrl_init(void)
{
  s_target = 0.0f; s_rpm_f = 0.0f; s_integral = 0.0f; s_duty = 0.0f; s_ff = 0.0f; s_tgt_ramp = 0.0f;
  s_last_ms = HAL_GetTick();
  cal_start();

  HAL_NVIC_SetPriority(CMD_UART_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(CMD_UART_IRQn);
  HAL_UART_Receive_IT(CMD_UART, &s_rx_byte, 1);
}

void rpm_ctrl_recalibrate(void)  { cal_start(); }

int rpm_ctrl_set_target(float rpm)
{
  if (s_state != ST_RUN) return 0;
  rpm = clampf(rpm, 0.0f, s_rpm_max);                     /* 上限 = 實測值 */
  /* 目標真的變了 (差 1 RPM 以上)，或剛從手動 duty 回到閉迴路：積分重來 */
  if (s_manual || fabsf(rpm - s_target) > 1.0f) s_integral = 0.0f;
  if (s_manual) s_tgt_ramp = rpm;                  /* 手動 -> 閉迴路：立即跟上新目標 */
  s_manual = 0U;
  s_target = rpm;
  return 1;
}

float rpm_ctrl_get_full_user(void)
{
  float full = (RPM_FULL_USER_OVERRIDE > 0.0f) ? RPM_FULL_USER_OVERRIDE
                                               : s_rpm_max * RPM_USER_HEADROOM;
  return (full > s_rpm_max) ? s_rpm_max : full;
}

int rpm_ctrl_set_percent(float pct)
{
  pct = clampf(pct, 0.0f, 100.0f);
  return rpm_ctrl_set_target(pct * 0.01f * rpm_ctrl_get_full_user());
}

float rpm_ctrl_get_target(void)  { return s_target; }
float rpm_ctrl_get_rpm(void)     { return s_fg_ok ? s_rpm_f : 0.0f; }   /* 沒訊號就回 0 */
float rpm_ctrl_get_duty(void)    { return s_duty; }
float rpm_ctrl_get_min_rpm(void) { return s_rpm_min; }
float rpm_ctrl_get_max_rpm(void) { return s_rpm_max; }
int   rpm_ctrl_is_ready(void)    { return s_state == ST_RUN; }
int   rpm_ctrl_is_manual(void)   { return s_manual; }
int   rpm_ctrl_is_calibrating(void) { return s_state == ST_CAL; }
int   rpm_ctrl_is_failed(void)      { return s_state == ST_ERR; }
int   rpm_ctrl_is_csv_logging(void) { return s_log_csv; }
void  rpm_ctrl_log(const char *s)   { uart_print(s); }
void  rpm_ctrl_print_status(void) { print_status(); }

/* 手動 duty (開迴路)：直接指定實際輸出的 PWM duty (0.0 ~ 100.0 %，超出會夾住)。
 * 不經前饋與 PI，轉速仍會量測。校正中不接受；校正失敗 (ST_ERR) 時可用。
 * 之後 R / P / X (rpm_ctrl_set_target) 會回到閉迴路，C 重新校正也會結束手動。 */
int rpm_ctrl_set_duty(float duty_pct)
{
  if (s_state == ST_CAL) return 0;
  if (!(duty_pct >= 0.0f)) duty_pct = 0.0f;        /* 也擋掉 NaN */
  if (duty_pct > 100.0f)   duty_pct = 100.0f;

  s_manual      = 1U;
  s_manual_duty = duty_pct;
  s_integral    = 0.0f;
  s_ff          = 0.0f;
  s_duty        = duty_pct;
  fan_set_duty_both_f(duty_pct);                   /* 立刻生效，不用等下一個 100 ms 週期 */
  return 1;
}

/* ---- UART 指令 --------------------------------------------------------- */
static void print_status(void)
{
  char out[160];

  /* CCR、ARR 都是 volatile 暫存器：分開讀，同一個敘述裡只放一次 volatile 存取
   * (否則 IAR 會報 Pa082，參數求值順序未定義)。
   * ccr/週期 是前風扇實際的 PWM 比例，應與 duty 一致。 */
  uint32_t ccr = __HAL_TIM_GET_COMPARE(&htim1, FAN_FRONT_PWM_CH);
  uint32_t per = __HAL_TIM_GET_AUTORELOAD(&htim1) + 1U;

  if (s_log_csv)
  {
    char out[160];
    snprintf(out, sizeof out,
             "%lu,%.1f,%.1f,%.2f,%.2f,%.2f,%lu,%lu,%.0f,%.0f\r\n",
             (unsigned long)HAL_GetTick(), (double)s_target, (double)rpm_ctrl_get_rpm(),
             (double)s_duty, (double)s_ff, (double)s_integral,
             (unsigned long)ccr, (unsigned long)per,
             (double)s_rpm_min, (double)s_rpm_max);
    uart_print(out);
    return;
  }

  if (s_state == ST_CAL)
  {
    snprintf(out, sizeof out, "CAL %u/%u rpm=%.0f duty=%.1f%%\r\n",
             (unsigned)(s_cal_idx + 1U), (unsigned)CAL_POINTS,
             (double)rpm_ctrl_get_rpm(), (double)s_duty);
  }
  else if (s_manual)
  {
    snprintf(out, sizeof out,
             "MAN duty=%.2f%% rpm=%.0f ccr=%lu/%lu range=%.0f..%.0f full=%.0f\r\n",
             (double)s_duty, (double)rpm_ctrl_get_rpm(),
             (unsigned long)ccr, (unsigned long)per,
             (double)s_rpm_min, (double)s_rpm_max, (double)rpm_ctrl_get_full_user());
  }
  else if (s_state == ST_ERR)
  {
    snprintf(out, sizeof out,
             "ERR calibration failed, no FG signal? rpm=%.0f. send C to retry\r\n",
             (double)rpm_ctrl_get_rpm());
  }
  else
  {
    static const char *const fl[] = { "OK", "LOW", "HIGH", "NOFG" };
    /* duty = ff + KP*err + i */
    snprintf(out, sizeof out,
             "%s target=%.0f rpm=%.0f duty=%.2f%% ff=%.2f i=%.2f ccr=%lu/%lu range=%.0f..%.0f full=%.0f\r\n",
             fl[s_flag], (double)s_target, (double)rpm_ctrl_get_rpm(), (double)s_duty,
             (double)s_ff, (double)s_integral,
             (unsigned long)ccr, (unsigned long)per,
             (double)s_rpm_min, (double)s_rpm_max, (double)rpm_ctrl_get_full_user());
  }
  uart_print(out);
}

/* 印出校正得到的 duty -> RPM 曲線 */
static void print_table(void)
{
  char out[48];

  if (s_state == ST_CAL)
  {
    uart_print("CAL in progress, wait for CAL done\r\n");
    return;
  }
  for (uint8_t i = 0; i < CAL_POINTS; i++)
  {
    snprintf(out, sizeof out, "T%u duty=%.1f%% rpm=%.0f\r\n",
             (unsigned)i, (double)cal_duty[i], (double)cal_rpm[i]);
    uart_print(out);
  }
}

/* 指令格式 (結尾換行，大小寫皆可)：
 *   R8000  -> 目標 8000 RPM
 *   P50    -> 目標 = 50% x 使用者滿轉 (轉速的 50%，不是 duty 50%)
 *   D17.5  -> 手動指定實際 PWM duty 17.5% (開迴路，不跑前饋 / PI；
 *             之後下 R / P / X 會回到閉迴路)
 *   S      -> 回報狀態
 *   X      -> 目標 0 (風扇降到它的最低轉速)
 *   C      -> 重新自動校正
 *   T      -> 印出校正曲線表                                           */
void rpm_ctrl_uart_poll(void)
{
  if (!s_cmd_ready) return;

  char cmd[24];
  memcpy(cmd, s_cmd, sizeof(cmd));
  s_cmd_ready = 0;

  char out[96];
  char op = cmd[0];
  if (op >= 'a' && op <= 'z') op = (char)(op - 'a' + 'A');
  float v = (float)atof(&cmd[1]);

  switch (op)
  {
    case 'R':
    case 'P':
      if ((op == 'R') ? rpm_ctrl_set_target(v) : rpm_ctrl_set_percent(v))
      {
        snprintf(out, sizeof out, "OK target=%.0f RPM\r\n", (double)s_target);
        uart_print(out);
      }
      else
      {
        uart_print("BUSY calibrating or calibration failed, send S\r\n");
      }
      break;
    case 'D':
    {
      char  *end;
      double d = strtod(&cmd[1], &end);
      if (end == &cmd[1] || !(d >= 0.0 && d <= 100.0))      /* 沒給數字 / 超出範圍 / NaN */
      {
        uart_print("ERR D<duty> needs a number 0..100, e.g. D17.5\r\n");
      }
      else if (rpm_ctrl_set_duty((float)d))
      {
        if (s_state == ST_ERR)     /* 校正失敗時 R/P/X 不接受，只有 C 能離開 */
          snprintf(out, sizeof out, "OK manual duty=%.2f%%, send C to recalibrate\r\n", (double)s_duty);
        else
          snprintf(out, sizeof out, "OK manual duty=%.2f%%, R/P/X returns to closed loop\r\n", (double)s_duty);
        uart_print(out);
      }
      else
      {
        uart_print("BUSY calibrating, send S\r\n");
      }
      break;
    }
    case 'X':
      if (rpm_ctrl_set_target(0.0f))
      {
        snprintf(out, sizeof out, "OK target=0, fan runs at its minimum %.0f RPM\r\n",
                 (double)s_rpm_min);
        uart_print(out);
      }
      else
      {
        uart_print("BUSY calibrating or calibration failed, send S\r\n");
      }
      break;
    case 'C':
      rpm_ctrl_recalibrate();
      uart_print("OK calibrating, fan will sweep 0..100%, progress is printed\r\n");
      break;
    case 'S':
      print_status();
      break;
    case 'T':
      print_table();
      break;
    case 'V':
      s_log_csv = (uint8_t)(s_log_csv ? 0U : 1U);
      if (s_log_csv) uart_print("CSV logging ON\r\n");
      else          uart_print("CSV logging OFF\r\n");
      break;
    case 'A':
      if (cmd[1] == '\0')          /* 裸 A -> 切換 */
      {
        uint8_t en = (uint8_t)(rpm_sweep_is_enabled() ? 0U : 1U);
        rpm_sweep_set_enable(en);
        if (en) uart_print("OK auto sweep ON\r\n");
        else    uart_print("OK auto sweep OFF (manual UART mode)\r\n");
      }
      else if (v > 0.0f)
      {
        rpm_sweep_set_enable(1U);
        uart_print("OK auto sweep ON\r\n");
      }
      else
      {
        rpm_sweep_set_enable(0U);
        uart_print("OK auto sweep OFF (manual UART mode)\r\n");
      }
      break;
    default:
      uart_print("ERR use R<rpm> / P<pct> / D<duty> / S / X / C / T / V / A0 / A1\r\n");
      break;
  }
}

/* ---- 控制核心 ---------------------------------------------------------- */
void rpm_ctrl_update(void)
{
  uint32_t now = HAL_GetTick();
  if ((now - s_last_ms) < RPM_CTRL_PERIOD_MS) return;
  float dt = (float)(now - s_last_ms) / 1000.0f;
  s_last_ms = now;

  /* 1) 量測 + 低通濾波。
   *    沒訊號時濾波值保持不動，不往 0 掉；否則 FG 恢復的瞬間，PI 會看到
   *    巨大誤差而把 duty 猛加，轉速就會衝過頭。
   *    (所以凡是要「當量測值」用 s_rpm_f 的地方，都要先檢查 s_fg_ok。)      */
  float meas = measure_rpm();
  s_fg_ok = (meas >= 1.0f) ? 1U : 0U;
  if (s_fg_ok) s_rpm_f += RPM_FILTER_ALPHA * (meas - s_rpm_f);

  if (s_state == ST_CAL)
  {
    cal_step(now);
    return;
  }
  if (s_manual)                      /* 手動 duty (開迴路)：只量測，不跑前饋 / PI */
  {
    s_ff   = 0.0f;
    s_duty = s_manual_duty;
    fan_set_duty_both_f(s_duty);
    return;
  }
  if (s_state == ST_ERR)
  {
    s_ff   = 0.0f;
    s_duty = 100.0f;                 /* 失敗時維持全速，避免過熱 */
    fan_set_duty_both_f(100.0f);
    return;
  }

  /* 2) 目標斜坡：避免大步設定造成超調 */
  {
    float step = RPM_TARGET_RAMP_RPS * dt;
    if (s_tgt_ramp < s_target)
      s_tgt_ramp = (s_tgt_ramp + step < s_target) ? (s_tgt_ramp + step) : s_target;
    else if (s_tgt_ramp > s_target)
      s_tgt_ramp = (s_tgt_ramp - step > s_target) ? (s_tgt_ramp - step) : s_target;
  }
  float tgt  = s_tgt_ramp;
  float span = s_rpm_max - s_rpm_min;
  if (span < 1.0f) span = 1.0f;

  if (tgt <= s_rpm_min)
  {
    s_flag = FL_LOW;
    s_integral = 0.0f;
    s_ff   = 0.0f;
    s_duty = 0.0f;
    fan_set_duty_both_f(0.0f);
    return;
  }

  /* 3) 前饋：由實測曲線反查 duty */
  float ff = ff_duty_from_rpm(tgt);
  s_ff = ff;

  /* 4) 讀不到 FG：只輸出前饋 + 目前積分，不再累積 */
  if (!s_fg_ok)
  {
    s_flag = FL_NOFG;
    s_duty = clampf(ff + s_integral, 0.0f, 100.0f);
    fan_set_duty_both_f(s_duty);
    return;
  }

  /* 5) PI 修正 (誤差以「轉速範圍的百分比」表示) */
  float err   = (tgt - s_rpm_f) * 100.0f / span;

  /* 死區：誤差很小時積分衰減，避免低速/高頻 hunting */
  if (fabsf(err) < RPM_ERR_DEADBAND_PCT)
  {
    s_integral *= 0.90f;
  }

  float i_new = clampf(s_integral + RPM_KI * err * dt, -RPM_I_LIMIT, RPM_I_LIMIT);
  float duty  = ff + RPM_KP * err + i_new;

  /* 6) 輸出限幅 + 條件式積分 (anti-windup)：飽和時不累積 */
  s_flag = FL_OK;
  if (duty >= 100.0f)
  {
    duty = 100.0f;
    if (err > 1.0f) s_flag = FL_HIGH;   /* 已全速仍達不到目標 */
    s_integral *= 0.85f;                 /* 飽和時衰減舊積分，減少超調 */
  }
  else if (duty < 0.0f)
  {
    duty = 0.0f;
  }
  else
  {
    s_integral = i_new;
  }

  s_duty = duty;
  fan_set_duty_both_f(duty);
}
