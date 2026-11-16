/*
 * fan_startup_test.h -- finds the minimum PWM duty that gets each fan
 * spinning FROM A DEAD STOP, by stepping duty up from start_duty and
 * watching fan_get_front_rpm()/fan_get_rear_rpm() for the first duty
 * where RPM crosses FAN_STARTUP_RPM_THRESHOLD.
 *
 * This measures the START (breakaway) threshold, not necessarily the
 * SUSTAIN threshold -- static friction is normally higher than kinetic
 * friction, so a fan already spinning can often be throttled back below
 * its own start duty before it stalls. If you also want that lower
 * "stops at" number, ask and the same table-walking idea extends with a
 * second, downward pass once the fan is already running.
 */

#ifndef FAN_STARTUP_TEST_H
#define FAN_STARTUP_TEST_H

#include <stdint.h>

#define FAN_STARTUP_DWELL_MS       3000UL  /* time to wait at each duty before
                                               concluding "still not spinning" */
#define FAN_STARTUP_RPM_THRESHOLD  50.0f   /* RPM above this = "it started" */

/* start_duty: first duty to try (e.g. 0, or 10 if you already know it's
   below threshold and want to save time). step_percent: duty increase per
   dwell (e.g. 1 for 1% resolution). */
void fan_startup_test_init(uint8_t start_duty, uint8_t step_percent);

/* call every main-loop iteration INSTEAD of fan_sweep_update() -- both
   call fan_set_duty_both(), running both at once would fight each other */
void fan_startup_test_update(void);

uint8_t fan_startup_test_done(void);          /* 1 once both fans found, or duty hit 100% */
uint8_t fan_startup_test_current_duty(void);  /* duty currently being tried  */
uint8_t fan_startup_test_front_duty(void);    /* 0xFF until the front fan starts */
uint8_t fan_startup_test_rear_duty(void);     /* 0xFF until the rear  fan starts */

#endif /* FAN_STARTUP_TEST_H */
