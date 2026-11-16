/*
 * fan_control.c -- see fan_control.h for wiring and CubeMX notes.
 *
 * Works either way USE_HAL_TIM_REGISTER_CALLBACKS is set in
 * stm32g4xx_hal_conf.h:
 *   0 (default) -> fan_control_ic_callback is reached through the global
 *                  weak HAL_TIM_IC_CaptureCallback() override below.
 *   1            -> fan_control_init() registers fan_control_ic_callback
 *                   directly on htim2 via HAL_TIM_RegisterCallback(); the
 *                   global weak override is compiled out, since it would
 *                   never be called once a callback is registered.
 */

#include "fan_control.h"

extern TIM_HandleTypeDef htim1;   /* PWM out: front fan (advanced-control) */
extern TIM_HandleTypeDef htim2;   /* IC: CH1 = front FG, CH2 = rear FG     */
extern TIM_HandleTypeDef htim8;   /* PWM out: rear fan  (advanced-control) */

/* ------------------------------ tach --------------------------------- */

#define TACH_AVG_N 4U

typedef struct {
    uint32_t last_capture;   /* TIM2 counter value at the last edge         */
    uint32_t last_edge_ms;   /* HAL_GetTick() at the last edge (staleness)  */
    uint8_t  have_last;      /* 0 until the first edge has been seen        */
    volatile float rpm;      /* most recently computed RPM (filtered)       */
    uint32_t periods[TACH_AVG_N];
    uint8_t  period_idx;
    uint8_t  period_count;
    uint32_t period_sum;
} tach_channel_t;

static tach_channel_t front_tach = {0, 0, 0, 0.0f};
static tach_channel_t rear_tach  = {0, 0, 0, 0.0f};

static void tach_update(tach_channel_t *ch, uint32_t capture_value)
{
    ch->last_edge_ms = HAL_GetTick();

    if (!ch->have_last) {
        ch->last_capture = capture_value;
        ch->have_last = 1;
        ch->period_idx = 0;
        ch->period_count = 0;
        ch->period_sum = 0;
        return;
    }

    uint32_t delta_ticks = capture_value - ch->last_capture;
    ch->last_capture = capture_value;

    if (delta_ticks == 0) {
        return;
    }

    /* 滑動平均週期，降低單週期量測雜訊 */
    if (ch->period_count >= TACH_AVG_N) {
        ch->period_sum -= ch->periods[ch->period_idx];
    } else {
        ch->period_count++;
    }
    ch->periods[ch->period_idx] = delta_ticks;
    ch->period_sum += delta_ticks;
    ch->period_idx = (uint8_t)((ch->period_idx + 1U) % TACH_AVG_N);

    float avg_delta = (float)(ch->period_sum / ch->period_count);
    ch->rpm = (60.0f / (float)TACH_PULSES_PER_REV)
              * (float)TACH_TIMER_CLOCK_HZ / avg_delta;
}

static float tach_read_rpm(const tach_channel_t *ch)
{
    if (!ch->have_last) {
        return 0.0f;
    }
    if ((HAL_GetTick() - ch->last_edge_ms) > TACH_TIMEOUT_MS) {
        return 0.0f;
    }
    return ch->rpm;
}

/* registered (or weak-overridden) for TIM2 only -- front/rear is a
   per-CHANNEL distinction, so this check stays regardless of which
   mechanism gets us called */
void fan_control_ic_callback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance != TIM2) {
        return;
    }

    if (htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1) {
        tach_update(&front_tach, HAL_TIM_ReadCapturedValue(htim, TIM_CHANNEL_1));
    } else if (htim->Channel == HAL_TIM_ACTIVE_CHANNEL_2) {
        tach_update(&rear_tach, HAL_TIM_ReadCapturedValue(htim, TIM_CHANNEL_2));
    }
}

#if !(USE_HAL_TIM_REGISTER_CALLBACKS == 1)
/* global weak override path -- only compiled in when callback
   registration is NOT in use, since it would otherwise never fire */
void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
    fan_control_ic_callback(htim);
}
#endif

/* ------------------------------ PWM ---------------------------------- */

static void pwm_set_duty(TIM_HandleTypeDef *htim, uint32_t channel, uint8_t pct)
{
    if (pct > 100U) {
        pct = 100U;
    }

    uint32_t arr = __HAL_TIM_GET_AUTORELOAD(htim);
    uint32_t ccr = ((arr + 1U) * (uint32_t)pct) / 100U;

    __HAL_TIM_SET_COMPARE(htim, channel, ccr);
}

/* High-resolution duty (0.0 ~ 100.0 %).  Resolution = 1/(ARR+1) = 1/6800 = 0.0147 %
   at ARR = 6799.  100 % -> CCR = ARR+1 (output held at its active level).
   This is the strong definition declared in fan_control.h; without it the linker
   silently falls back to a 1 %-resolution weak stub. */
static void pwm_set_duty_f(TIM_HandleTypeDef *htim, uint32_t channel, float pct)
{
    if (!(pct > 0.0f)) {            /* also catches NaN */
        pct = 0.0f;
    }
    if (pct > 100.0f) {
        pct = 100.0f;
    }

    uint32_t arr = __HAL_TIM_GET_AUTORELOAD(htim);
    uint32_t ccr = (uint32_t)(pct * 0.01f * (float)(arr + 1U) + 0.5f);
    if (ccr > arr + 1U) {
        ccr = arr + 1U;
    }

    __HAL_TIM_SET_COMPARE(htim, channel, ccr);
}

void fan_set_duty_both_f(float duty_percent)
{
    pwm_set_duty_f(&htim1, FAN_FRONT_PWM_CH, duty_percent);
    pwm_set_duty_f(&htim8, FAN_REAR_PWM_CH,  duty_percent);
}

void fan_control_init(void)
{
#if (USE_HAL_TIM_REGISTER_CALLBACKS == 1)
    /* must be called while htim2 is still READY/RESET, i.e. before
       HAL_TIM_IC_Start_IT() below puts it in a busy state */
    HAL_TIM_RegisterCallback(&htim2, HAL_TIM_IC_CAPTURE_CB_ID, fan_control_ic_callback);
#endif

    HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_1);          /* front FG */
    HAL_TIM_IC_Start_IT(&htim2, TIM_CHANNEL_2);          /* rear  FG */
    HAL_TIM_PWM_Start(&htim1, FAN_FRONT_PWM_CH);
    HAL_TIM_PWM_Start(&htim8, FAN_REAR_PWM_CH);
}

void fan_set_duty_front(uint8_t duty_percent)
{
    pwm_set_duty(&htim1, FAN_FRONT_PWM_CH, duty_percent);
}

void fan_set_duty_rear(uint8_t duty_percent)
{
    pwm_set_duty(&htim8, FAN_REAR_PWM_CH, duty_percent);
}

void fan_set_duty_both(uint8_t duty_percent)
{
    fan_set_duty_front(duty_percent);
    fan_set_duty_rear(duty_percent);
}

float fan_get_front_rpm(void) { return tach_read_rpm(&front_tach); }
float fan_get_rear_rpm(void)  { return tach_read_rpm(&rear_tach);  }