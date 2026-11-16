/*
 * fan_control.h -- Delta GFC0412DS-SM06B0G (front + rear fan) on NUCLEO-G431RB
 *
 *  PWM out, 25 kHz edge-aligned:
 *      TIM1_CH1 (PC0, AF2) -> front fan PWM input
 *      TIM8_CH1 (PC6, AF4) -> rear  fan PWM input
 *  Tach in, input capture on the 32-bit TIM2:
 *      TIM2_CH1 (PA0) -> front fan FG,  TIM2_CH2 (PA1) -> rear fan FG
 *      FG is open-collector: each line needs its own pull-up to 3.3 V.
 *
 * Set TACH_TIMER_CLOCK_HZ to your real TIM2 clock
 * (CubeMX > Clock Configuration > APB1 timer clocks; 170 MHz for the
 * PLL config in this project's SystemClock_Config(), APB1 prescaler = 1).
 */

#ifndef FAN_CONTROL_H
#define FAN_CONTROL_H

#include "main.h"
#include <stdint.h>

/* ---- adjust to match your project ---- */
#define TACH_TIMER_CLOCK_HZ   170000000UL   /* TIM2 input clock, Hz            */
#define TACH_PULSES_PER_REV   2U            /* standard for this fan's FG line */
#define TACH_TIMEOUT_MS       250U          /* no edge this long => report 0 RPM
                                               (2 pulses/rev: below ~120 RPM)  */
#define FAN_FRONT_PWM_CH      TIM_CHANNEL_1 /* on htim1 */
#define FAN_REAR_PWM_CH       TIM_CHANNEL_1 /* on htim8 */
/* --------------------------------------- */

void fan_control_init(void);

/* duty_percent: 0..100 (1% steps).  100 = output held active (no edges). */
void fan_set_duty_front(uint8_t duty_percent);
void fan_set_duty_rear(uint8_t duty_percent);
void fan_set_duty_both(uint8_t duty_percent);

/* High-resolution duty for both fans: 0.0 .. 100.0 %.
   Resolution is one timer count, 1/(ARR+1) = 0.015 % at ARR = 6799.
   rpm_ctrl.c calls this one; there is intentionally no fallback in
   rpm_ctrl.c, so a missing definition shows up as a link error instead of
   silently dropping back to 1 % steps. */
void fan_set_duty_both_f(float duty_percent);

/* RPM for each fan; 0.0f until the first full period is captured, and
   0.0f again if no edge has arrived in the last TACH_TIMEOUT_MS
   (fan stopped / FG disconnected) rather than showing a stale value. */
float fan_get_front_rpm(void);
float fan_get_rear_rpm(void);

/* called from HAL_TIM_IC_CaptureCallback (defined in fan_control.c) */
void fan_control_ic_callback(TIM_HandleTypeDef *htim);

#endif /* FAN_CONTROL_H */
