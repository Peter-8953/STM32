#include "fan_startup_test.h"
#include "fan_control.h"
#include "main.h"   /* HAL_GetTick() */

#define STARTUP_NOT_FOUND  0xFFU

static uint8_t  test_duty;
static uint8_t  test_step;
static uint32_t step_start_tick;
static uint8_t  front_start_duty;
static uint8_t  rear_start_duty;
static uint8_t  done;

void fan_startup_test_init(uint8_t start_duty, uint8_t step_percent)
{
    test_duty        = (start_duty > 100U) ? 100U : start_duty;
    test_step         = (step_percent == 0U) ? 1U : step_percent;
    front_start_duty  = STARTUP_NOT_FOUND;
    rear_start_duty   = STARTUP_NOT_FOUND;
    done              = 0U;
    step_start_tick   = HAL_GetTick();
    fan_set_duty_both(test_duty);
}

void fan_startup_test_update(void)
{
    if (done) {
        return;
    }

    if (front_start_duty == STARTUP_NOT_FOUND && fan_get_front_rpm() > FAN_STARTUP_RPM_THRESHOLD) {
        front_start_duty = test_duty;
    }
    if (rear_start_duty == STARTUP_NOT_FOUND && fan_get_rear_rpm() > FAN_STARTUP_RPM_THRESHOLD) {
        rear_start_duty = test_duty;
    }

    if ((front_start_duty != STARTUP_NOT_FOUND && rear_start_duty != STARTUP_NOT_FOUND)
        || test_duty >= 100U) {
        done = 1U;
        return;
    }

    if ((HAL_GetTick() - step_start_tick) >= FAN_STARTUP_DWELL_MS) {
        test_duty = (uint8_t)((test_duty + test_step > 100U) ? 100U : test_duty + test_step);
        fan_set_duty_both(test_duty);
        step_start_tick = HAL_GetTick();
    }
}

uint8_t fan_startup_test_done(void)         { return done; }
uint8_t fan_startup_test_current_duty(void) { return test_duty; }
uint8_t fan_startup_test_front_duty(void)   { return front_start_duty; }
uint8_t fan_startup_test_rear_duty(void)    { return rear_start_duty; }
